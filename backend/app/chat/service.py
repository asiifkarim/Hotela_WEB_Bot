from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator

from app.chat.guards import GuardResult, apply_guards
from app.chat.smalltalk import check
from app.config import Settings
from app.db import SessionLocal
from app.llm.client import LLMClient
from app.logging_setup import safe_message
from app.models import Conversation, Unanswered
from app.rag.chunker import section_text
from app.rag.retriever import RetrievedChunk, retrieve
from app.text import (
    ARABIC_BLOCK,
    chunk_body,
    clean_markdown,
    detect_language,
    roman_urdu_score,
    script_of,
)

logger = logging.getLogger(__name__)

ACTION_RE = re.compile(r"<<ACTION:(lead_form|handoff)>>")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# The reply used when nothing in the knowledge base answers the question.
# The wording is fixed on purpose: it is the one answer that must never
# depend on a provider being available.
HANDOFF_TEMPLATES = {
    "en": "I'm not sure from the available Hotela information. Please contact the Hotela team at {contact}.",
    "ru": "Mujhe yeh baat available Hotela information se confirm nahi ho saki. Please contact the Hotela team at {contact}.",
    "ur": "مجھے یہ معلومات موجود ہوٹیلا معلومات سے تصدیق نہیں ہو سکی۔ براہِ کرم ہوٹیلا ٹیم سے رابطہ کریں: {contact}",
}
UNKNOWN_TEMPLATES = {
    "en": "I'm not sure from the available Hotela information.",
    "ru": "Mujhe yeh baat available Hotela information mein nahi mili.",
    "ur": "یہ معلومات دستیاب ہوٹیلا معلومات میں نہیں ملیں۔",
}

# Phrases in an answer that mean the visitor has to talk to the team. They
# decide whether the handoff action is offered next to a documented answer.
HANDOFF_OFFER_MARKERS = (
    "contact the hotela team",
    "contact hotela",
    "go to the hotela team",
    "hotelaapp@gmail.com",
    "not sure",
)

# Knowledge-base sections that document a gap. Their heading carries the
# meaning, so the heading is kept in the reply.
GAP_SECTION_MARKERS = ("not confirmed", "not documented", "not published", "not specified")

# A body that opens by declaring the answer unknown. A statement in the
# middle of an answer ("annual prices are not published, and the price for
# additional branches is not published") is not a gap: that answer is
# documented, with one detail in it that is not.
GAP_BODY_STARTS = (
    "this is not confirmed",
    "this is not documented",
    "this is not published",
    "this cannot be confirmed",
    "not confirmed",
    "not documented",
    "not published",
)

# The sentence added when the knowledge base documents a gap instead of an
# answer. It is part of the answer, not a decoration: the visitor has to know
# that the team has to answer.
GAP_NOTICES = {
    "en": "That detail is not documented in the Hotela information. Please contact the Hotela team at {contact}.",
    "ru": "Yeh detail Hotela information mein documented nahi hai. Please contact the Hotela team at {contact}.",
    "ur": "یہ تفصیل ہوٹیلا معلومات میں دستیاب نہیں ہے۔ براہِ کرم ہوٹیلا ٹیم سے رابطہ کریں: {contact}",
}

# The sentence added when the answer is documented but says that one detail
# in it is not published ("Annual prices are not published"). The detail is
# named in the answer itself, so the notice stays general: it must not claim
# that the detail the visitor asked about is the one that is missing.
DECLARED_GAP_NOTICES = {
    "en": (
        "Some details are not published in the Hotela information. "
        "If your question is about one of them, please contact the Hotela team at {contact}."
    ),
    "ru": (
        "Kuch details Hotela information mein published nahi hain. "
        "Agar aapka sawal in mein se kisi ek ka hai, to Please contact the Hotela team at {contact}."
    ),
    "ur": (
        "کچھ تفصیلات ہوٹیلا معلومات میں شائع نہیں ہیں۔ "
        "اگر آپ کا سوال ان میں سے کسی ایک کے بارے میں ہے تو براہِ کرم ہوٹیلا ٹیم سے رابطہ کریں: {contact}"
    ),
}

# A sentence that says a detail is unknown: "Annual prices are not
# published." The visitor asked about that detail, so the answer has to say
# so and offer the team - even though the rest of the section is documented.
GAP_DECLARATION_RE = re.compile(
    r"\b(?:is|are|was|were)\s+not\s+(?:confirmed|published|documented|specified)\b",
    re.IGNORECASE,
)

# Knowledge-base text that addresses the assistant instead of the visitor
# ("the assistant must not promise any of them"). It is guidance, not an
# answer, and it must never turn a documented answer into a handoff.
ASSISTANT_GUIDANCE_RE = re.compile(
    r"the assistant\b|must not be claimed|must not promise|do not promise|"
    r"never quote|offer the hotela team|say the details are",
    re.IGNORECASE,
)

# How much a same-language chunk is preferred over the raw retrieval ranking.
# It is a factor on the retrieval score, so it can reorder neighbours without
# overturning the ranker that produced them.
LANGUAGE_WEIGHT = 0.12


class ChatService:
    """The chat pipeline: guards, small talk, retrieval, generation, fallback.

    Every answer comes from the knowledge base. When the provider is down the
    service still answers from the same retrieved chunks, so a visitor is never
    told something the knowledge base does not contain.
    """

    def __init__(self, settings: Settings, collection, embedder, llm: LLMClient | None) -> None:
        self.settings = settings
        self.collection = collection
        self.embedder = embedder
        self.llm = llm
        self._core_facts_cache: str | None = None

    # ------------------------------------------------------------------ #
    # settings helpers
    # ------------------------------------------------------------------ #
    def _option(self, name: str, default):
        """Read a setting, falling back to the default.

        The service is also driven by tests and by the evaluator with reduced
        settings objects, so a new option must never be mandatory.
        """
        return getattr(self.settings, name, default)

    # ------------------------------------------------------------------ #
    # curated facts
    # ------------------------------------------------------------------ #
    def _support_block(self) -> str:
        path = self.settings.kb_dir / "app_how_to.md"
        return section_text(path, "Support and contact")

    def _contact(self) -> str:
        """The contact address, read from the knowledge base so it cannot drift."""
        match = EMAIL_RE.search(self._support_block())
        if match:
            return match.group(0)
        return str(self._option("handoff_email", "hotelaapp@gmail.com"))

    def _core_facts(self, include_contact: bool = False) -> str:
        """Return curated KB facts, adding contact data only when requested."""
        cache_key = "with_contact" if include_contact else "without_contact"
        if self._core_facts_cache is not None and cache_key == "without_contact":
            return self._core_facts_cache
        plans = json.loads((self.settings.kb_dir / "plans.json").read_text(encoding="utf-8"))
        plan_text = "\n".join(
            f"{p['name']}: {plans['currency']} {p['price']} per branch for {p['duration_months']} months; {', '.join(p['features'])}"
            for p in plans["plans"]
        )
        facts = f"Plans:\n{plan_text}"
        if include_contact:
            facts += f"\nContact source:\n{self._support_block()}"
        if not include_contact:
            self._core_facts_cache = facts
        return facts

    @staticmethod
    def _asks_for_contact(message: str) -> bool:
        """Whether the visitor explicitly asks for a contact channel."""
        return bool(
            re.search(
                r"\b(contact|email|e-mail|phone|number|call|whatsapp|facebook|instagram|linkedin|support)\b",
                message or "",
                re.IGNORECASE,
            )
        )

    def _filter_contact_chunks(
        self, matches: list[RetrievedChunk], include_contact: bool
    ) -> list[RetrievedChunk]:
        if include_contact:
            return matches
        return [
            chunk
            for chunk in matches
            if not re.search(
                r"\b(support and contact|contact|email|phone|whatsapp|facebook|instagram|linkedin)\b",
                f"{chunk.metadata.get('section', '')} {chunk.text}",
                re.IGNORECASE,
            )
        ]

    # ------------------------------------------------------------------ #
    # persistence
    # ------------------------------------------------------------------ #
    def _save(self, session_id: str, role: str, message: str) -> None:
        with SessionLocal() as db:
            db.add(Conversation(session_id=session_id, role=role, message=message))
            db.commit()

    def _log_unanswered(self, session_id: str, message: str) -> None:
        with SessionLocal() as db:
            db.add(Unanswered(session_id=session_id, question=message))
            db.commit()

    # ------------------------------------------------------------------ #
    # grounded answer (used when the provider cannot answer)
    # ------------------------------------------------------------------ #
    def _language_affinity(self, text: str, language: str) -> int:
        """How well a chunk's language matches the visitor's language.

        English and Roman Urdu share the Latin script, so the script alone
        cannot tell them apart: Roman Urdu is detected by its markers.
        """
        if language == "ur":
            if ARABIC_BLOCK.search(text or ""):
                return 1
            return -1 if script_of(text) == "latin" else 0
        if language == "ru":
            score = roman_urdu_score(text)
            if score >= 2:
                return 1
            return 0 if score == 1 else -1
        return 1 if script_of(text) == "latin" else -1

    def _rank_for_language(self, matches: list[RetrievedChunk], language: str) -> list[RetrievedChunk]:
        """Order chunks by relevance, with a nudge towards the visitor's language.

        The nudge is a factor on the retrieval score, never a replacement for
        it: the ranker that produced the order (vector, or vector fused with
        BM25) keeps its say, and only near neighbours are swapped.
        """

        def rank(chunk: RetrievedChunk) -> float:
            base = chunk.score or chunk.similarity
            return base * (1.0 + LANGUAGE_WEIGHT * self._language_affinity(chunk.text, language))

        return sorted(matches, key=rank, reverse=True)

    @staticmethod
    def _normalize_question(text: str) -> str:
        return re.sub(r"[^a-z0-9\s]", "", (text or "").lower()).strip()

    def _rank_context(self, query: str, matches: list[RetrievedChunk], language: str) -> list[RetrievedChunk]:
        """Put an exact FAQ/section match ahead of neighboring semantic hits."""
        normalized_query = self._normalize_question(query)
        query_terms = set(normalized_query.split())

        def rank(chunk: RetrievedChunk) -> tuple[int, float]:
            section = self._normalize_question(str(chunk.metadata.get("section", "")))
            exact = int(section == normalized_query)
            overlap = len(query_terms & set(section.split()))
            base = chunk.score or chunk.similarity
            language_score = base * (1.0 + LANGUAGE_WEIGHT * self._language_affinity(chunk.text, language))
            return exact, overlap + language_score

        return sorted(matches, key=rank, reverse=True)

    def _is_gap_chunk(self, chunk: RetrievedChunk) -> bool:
        """Does this chunk document a gap instead of an answer?

        The knowledge base marks its gaps with a heading ("Not confirmed for
        bookings", "What is not documented about finances"), and a few FAQ
        answers open with "This is not confirmed." A sentence in the middle of
        an answer is not a gap - that answer is documented, with one detail in
        it that is not.
        """
        section = str(chunk.metadata.get("section", "")).lower()
        if any(marker in section for marker in GAP_SECTION_MARKERS):
            return True
        body = chunk_body(chunk.text).strip().lower()
        return any(body.startswith(marker) for marker in GAP_BODY_STARTS)

    def _declares_gap(self, chunk: RetrievedChunk) -> bool:
        """Does this chunk say that the detail in question is unknown?

        A documented answer can carry one unpublished detail ("Annual prices
        are not published, and the price for additional branches beyond the
        first is not published"). The visitor asked about that detail, so the
        answer has to say so and offer the team. Sections that address the
        assistant instead of the visitor are guidance, not answers, and never
        turn a documented answer into a handoff.
        """
        body = chunk_body(chunk.text).strip()
        if not body or ASSISTANT_GUIDANCE_RE.search(body):
            return False
        return bool(GAP_DECLARATION_RE.search(body))

    def _render_plan_chunk(self, chunk: RetrievedChunk, body: str) -> str:
        """plans.json chunks are key/value blocks; render them as sentences."""
        fields: dict[str, str] = {}
        for line in body.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip().lower()] = value.strip()
        name = fields.get("plan") or str(chunk.metadata.get("section", ""))
        price = re.sub(r"(\d)(?=(\d{3})+$)", r"\1,", fields.get("price", ""))
        duration = fields.get("duration", "")
        billing = fields.get("billing", "")
        features = fields.get("features", "")
        parts = [f"{name}: {price}" if price else name]
        if duration:
            parts.append(f"for {duration}")
        text = ", ".join(part for part in parts if part) + "."
        if billing:
            text += f" {billing}."
        if features:
            text += f" Features: {features}."
        return text

    def _render_chunk(self, chunk: RetrievedChunk) -> str:
        """Turn one retrieved chunk into readable prose, without its heading."""
        body = chunk_body(chunk.text)
        if not body:
            return ""
        if str(chunk.metadata.get("file", "")) == "plans.json":
            if str(chunk.metadata.get("section", "")) == "comparison":
                rows = [line.strip()[2:].strip() for line in body.splitlines() if line.strip().startswith("- ")]
                return " ".join(rows)
            return self._render_plan_chunk(chunk, body)
        text = clean_markdown(body)
        if self._is_gap_chunk(chunk):
            # The heading is the statement that this is a gap; dropping it
            # would turn a refusal into a confident answer.
            heading = str(chunk.metadata.get("section", "")).split(">")[-1].strip()
            if heading:
                text = f"{heading}: {text}"
        return text

    def _grounded_answer(
        self, matches: list[RetrievedChunk], language: str, query: str = ""
    ) -> tuple[str, bool, bool]:
        """Compose an answer from the retrieved chunks only.

        The answer quotes the knowledge base; it never adds a fact of its own.
        Several chunks are combined because some visitor questions need two
        sections of the knowledge base to be answered at all.

        The best match decides what the answer is:

        * a gap section ("Not confirmed for bookings") means the knowledge base
          documents a gap - only the gap sections are kept, and the visitor is
          handed to the team;
        * a section that says a detail is not published ("Annual prices are not
          published") is documented, but not for the detail the visitor asked
          about - the answer keeps the section and says the team has to answer
          that part;
        * anything else is a plain answer.

        Returns the answer, whether it documents a gap, and whether it
        declares an unpublished detail.
        """
        if not matches:
            return "", False, False
        ordered = self._rank_for_language(matches, language)
        if query:
            normalized_query = self._normalize_question(query)
            exact = [
                chunk
                for chunk in ordered
                if self._normalize_question(str(chunk.metadata.get("section", ""))) == normalized_query
            ]
            if exact:
                ordered = exact + [chunk for chunk in ordered if chunk not in exact]
        max_chunks = min(1, int(self._option("fallback_max_chunks", 1)))
        max_chars = int(self._option("fallback_max_chars", 700))
        best = ordered[0]
        floor = best.similarity - 0.15

        blocks: list[str] = []
        chunks: list[RetrievedChunk] = []
        seen: set[str] = set()
        for chunk in ordered:
            if len(blocks) >= max_chunks:
                break
            if chunk.similarity < floor:
                break
            block = self._render_chunk(chunk)
            if not block:
                continue
            key = " ".join(block.lower().split())
            if key in seen:
                continue
            seen.add(key)
            blocks.append(block)
            chunks.append(chunk)
            if sum(len(item) for item in blocks) >= max_chars:
                break
        if not blocks:
            return "", False, False
        gap = self._is_gap_chunk(chunks[0])
        declares = not gap and self._declares_gap(chunks[0])
        if gap:
            # The best match is a gap: quoting unrelated sections next to it
            # would make an undocumented detail look documented.
            pairs = [(block, chunk) for block, chunk in zip(blocks, chunks) if self._is_gap_chunk(chunk)]
            if pairs:
                blocks = [block for block, _chunk in pairs]
        else:
            # The question is documented. A gap section that came along is a
            # footnote about something else, not the answer.
            kept = [block for block, chunk in zip(blocks, chunks) if not self._is_gap_chunk(chunk)]
            if kept:
                blocks = kept
        return " ".join(blocks).strip(), gap, declares

    # ------------------------------------------------------------------ #
    # request pipeline
    # ------------------------------------------------------------------ #
    def stream(self, session_id: str, message: str, history: list[dict] | None = None) -> Iterator[tuple[str, str]]:
        started = time.perf_counter()
        guard: GuardResult = apply_guards(
            message,
            history,
            max_chars=int(self._option("max_message_chars", 500)),
            max_turns=int(self._option("llm_history_turns", 10)),
        )
        self._save(session_id, "user", guard.message)
        language = detect_language(guard.message)

        if guard.injection or guard.off_topic:
            answer = "I can help with Hotela's hotel and restaurant management product, plans, and support."
            yield "token", answer
            yield "done", ""
            self._save(session_id, "assistant", answer)
            self._log_request(language, [], started, outcome="redirect", question=guard.message)
            return

        last_bot_message = next(
            (turn.get("content", "") for turn in reversed(guard.history) if turn.get("role") == "assistant"),
            None,
        )
        smalltalk = check(guard.message, last_bot_message=last_bot_message)
        if smalltalk.reply:
            self._save(session_id, "assistant", smalltalk.reply)
            yield "token", smalltalk.reply
            yield "done", ""
            self._log_request(language, [], started, outcome="smalltalk", question=guard.message)
            return

        query = smalltalk.query
        if self._option("query_rewrite", False):
            try:
                query = self.llm.rewrite_query(smalltalk.query, guard.history)
            except Exception as error:
                logger.warning("Query rewrite failed; retrieving with the original question: %s", error)

        matches = retrieve(self.collection, self.embedder, query, self.settings.top_k, self.settings.min_similarity)
        contact_requested = self._asks_for_contact(guard.message)
        matches = self._filter_contact_chunks(matches, contact_requested)
        logger.debug(
            "retrieved chunks",
            extra={
                "event": "retrieval",
                "query": safe_message(query),
                "chunks": [
                    {
                        "file": m.metadata.get("file"),
                        "section": m.metadata.get("section"),
                        "similarity": round(m.similarity, 4),
                        "score": round(m.score, 4),
                    }
                    for m in matches
                ],
            },
        )
        # The context is ordered by language affinity, so the material written
        # in the visitor's own language comes first: it anchors the reply.
        # Rank generation context against the visitor's original wording.
        # Query rewriting is useful for retrieval, but a rewrite can otherwise
        # make a direct FAQ heading lose to a neighboring semantic result.
        ordered = self._rank_context(guard.message, matches, language)
        normalized_question = self._normalize_question(guard.message)
        exact_matches = [
            match
            for match in ordered
            if self._normalize_question(str(match.metadata.get("section", ""))) == normalized_question
        ]
        context_matches = exact_matches[:1] if exact_matches else ordered[:3]
        context = "\n\n".join(
            f"[{m.metadata.get('file')} / {m.metadata.get('section')}] {m.text}" for m in context_matches
        )

        if matches:
            yield "status", "grounded_answer"
            unique_sources = []
            seen_src = set()
            for m in matches:
                file_name = m.metadata.get("file", "")
                section = m.metadata.get("section", "")
                urls = m.metadata.get("source_urls", [])
                url = urls[0] if urls else ""
                key = (file_name, section)
                if key not in seen_src:
                    seen_src.add(key)
                    unique_sources.append({
                        "file": file_name,
                        "section": section,
                        "url": url,
                        "similarity": round(m.similarity, 2),
                    })
            yield "sources", json.dumps(unique_sources)
        else:
            yield "status", "insufficient_context"

        # A question the knowledge base does not cover is answered by handing
        # the visitor to the team, not by the model guessing.
        answer_min = float(self._option("retrieval_answer_min_similarity", self.settings.min_similarity))
        best_similarity = max((m.similarity for m in matches), default=0.0)
        confident = bool(matches) and best_similarity >= answer_min
        if not confident:
            answer = (
                HANDOFF_TEMPLATES.get(language, HANDOFF_TEMPLATES["en"]).format(contact=self._contact())
                if contact_requested
                else UNKNOWN_TEMPLATES.get(language, UNKNOWN_TEMPLATES["en"])
            )
            self._log_unanswered(session_id, guard.message)
            yield "token", answer
            yield "action", "handoff"
            yield "done", ""
            self._save(session_id, "assistant", answer)
            self._log_request(language, matches, started, outcome="handoff", question=guard.message)
            return

        parts: list[str] = []
        actions: list[str] = []
        provider_error = ""
        try:
            final_prompt_facts = self._core_facts(include_contact=contact_requested)
            for token in self.llm.stream_answer(
                guard.message, context, final_prompt_facts, guard.history
            ):
                action_match = ACTION_RE.search(token)
                if action_match:
                    clean = token[: action_match.start()] + token[action_match.end():]
                    if clean:
                        parts.append(clean)
                        yield "token", clean
                    actions.append(action_match.group(1))
                    yield "action", action_match.group(1)
                else:
                    parts.append(token)
                    yield "token", token
        except Exception as error:
            provider_error = f"{type(error).__name__}: {error}"
            logger.warning("Provider failed; using the grounded knowledge base: %s", provider_error)
            if not parts:
                answer, gap, declares = self._grounded_answer(matches, language, guard.message)
                if gap or declares:
                    notices = GAP_NOTICES if gap else DECLARED_GAP_NOTICES
                    notice = notices.get(language, notices["en"]).format(contact=self._contact())
                    answer = f"{answer} {notice}".strip()
                    actions.append("handoff")
                elif not answer:
                    answer = (
                        HANDOFF_TEMPLATES.get(language, HANDOFF_TEMPLATES["en"]).format(contact=self._contact())
                        if contact_requested
                        else UNKNOWN_TEMPLATES.get(language, UNKNOWN_TEMPLATES["en"])
                    )
                    actions.append("handoff")
                elif any(marker in answer.lower() for marker in HANDOFF_OFFER_MARKERS):
                    actions.append("handoff")
                parts.append(answer)
                yield "token", answer
                for action in actions:
                    yield "action", action

        answer = "".join(parts).strip()
        self._save(session_id, "assistant", answer)
        yield "done", ""
        self._log_request(
            language,
            matches,
            started,
            outcome="answered" if not provider_error else "fallback",
            question=guard.message,
            provider_error=provider_error,
        )

    # ------------------------------------------------------------------ #
    # observability
    # ------------------------------------------------------------------ #
    def _log_request(
        self,
        language: str,
        matches: list[RetrievedChunk],
        started: float,
        *,
        outcome: str,
        question: str = "",
        provider_error: str = "",
    ) -> None:
        """One structured record per request. No secrets, no personal data."""
        usage = getattr(self.llm, "last_usage", None) if self.llm is not None else None
        record = {
            "event": "chat_request",
            "outcome": outcome,
            "language": language,
            "question": safe_message(question),
            "chunks": len(matches),
            "chunk_ids": [
                f"{m.metadata.get('file')}>{m.metadata.get('section')}:{round(m.similarity, 3)}" for m in matches
            ],
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "model": str(self._option("llm_model", "")),
        }
        if usage:
            record["tokens"] = usage
        if provider_error:
            record["error"] = provider_error
        logger.info("chat request completed", extra=record)
