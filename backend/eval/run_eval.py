"""Evaluate the Hotela assistant and fail loudly when it regresses.

Two halves, measured separately so a provider outage cannot masquerade as a
quality drop:

1. Retrieval half (always measured): the local embedding model and the Chroma
   index are used exactly as the service uses them, so hit@1, hit@k, MRR, the
   "did we retrieve the section that documents the gap" rate and the retrieval
   latency percentiles are real measurements. The raw visitor question is used,
   because the LLM query-rewrite step needs the provider; pass --rewrite to
   measure with rewriting when a provider is available.
2. Generation half (measured only with a responsive provider): answers are
   driven through the real /api/chat SSE surface and scored for fact
   correctness, faithfulness (the answer states at least one checked fact and
   every fact it states is traceable to the retrieved context or the plan
   facts), unsupported numbers, handoff behaviour, redirect behaviour and
   language. A preflight call decides whether this half can run.
3. Fallback half (always measured): the same questions are answered with the
   provider forced to fail, so the degraded path - the one a visitor gets when
   the model is unreachable - is scored with the same yardstick. This is what
   keeps an outage from turning into wrong answers.

Exit codes:
    0  success (generation half reported as unmeasured when the provider is down)
    1  regression against the baseline, beyond --tolerance
    2  the evaluation set or the knowledge base is invalid (missing file or section)
    3  --require-generation was passed but the provider is unavailable

Usage:
    python backend/eval/run_eval.py
    python backend/eval/run_eval.py --limit 5            # quick smoke run
    python backend/eval/run_eval.py --no-generation
    python backend/eval/run_eval.py --update-baseline    # after an intended change
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings  # noqa: E402
from app.embeddings import create_embedder  # noqa: E402
from app.rag.chunker import kb_documents, section_names, token_estimator  # noqa: E402
from app.rag.index import collection_info, load_collection  # noqa: E402
from app.rag.retriever import RetrievedChunk, retrieve  # noqa: E402

QUESTIONS = ROOT / "backend" / "eval" / "questions.yaml"
BASELINE = ROOT / "backend" / "eval" / "baseline.json"
RESULTS_DIR = ROOT / "backend" / "eval" / "results"
KINDS = {"easy", "multi-step", "handoff", "language", "injection", "smalltalk"}
EXPECTS = {"answer", "handoff", "redirect", "smalltalk"}
METRIC_KEYS = ("hit_1", "hit_k", "mrr", "idk_context_hit_k")
FALLBACK_METRIC_KEYS = (
    "answer_correct_rate",
    "faithfulness_rate",
    "handoff_rate",
    "redirect_rate",
    "smalltalk_rate",
    "language_rate",
)
LANGUAGE_MARKERS = {
    "ru": ("hai", "haan", "hain", "kya", "nahi", "ke", "ka", "aur", "mein"),
    "ur": ("ہے", "ہیں", "کیا", "جی", "اور", "میں", "کے", "نہیں"),
}
ANSWER_MARKERS = {
    "handoff": ("not sure", "not confirmed", "contact", "hotelaapp@gmail.com", "355 5871667", "team"),
    "redirect": ("help with hotela", "hotela"),
}
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


# --------------------------------------------------------------------------- #
# evaluation set
# --------------------------------------------------------------------------- #
def load_questions(path: Path) -> tuple[list[dict], list[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    errors: list[str] = []
    ids: set[str] = set()
    for index, item in enumerate(questions, 1):
        label = item.get("id") or f"question #{index}"
        if not item.get("id"):
            errors.append(f"{label}: missing id")
        elif item["id"] in ids:
            errors.append(f"{label}: duplicate id")
        else:
            ids.add(item["id"])
        if not item.get("question"):
            errors.append(f"{label}: missing question")
        if item.get("kind") not in KINDS:
            errors.append(f"{label}: kind must be one of {sorted(KINDS)}")
        if item.get("expect") not in EXPECTS:
            errors.append(f"{label}: expect must be one of {sorted(EXPECTS)}")
        if not item.get("expected_answer"):
            errors.append(f"{label}: missing expected_answer")
        if item.get("expect") == "answer" and not item.get("answer_facts"):
            errors.append(f"{label}: expect: answer needs answer_facts")
        if item.get("expect") in {"redirect", "smalltalk"} and (item.get("sources") or item.get("answer_facts")):
            errors.append(f"{label}: {item['expect']} questions must not declare sources or facts")
        if item.get("expect") == "answer" and not item.get("sources"):
            errors.append(f"{label}: expect: answer needs at least one source section")
    if not 40 <= len(questions) <= 60:
        errors.append(f"the set has {len(questions)} questions; keep it between 40 and 60")
    return questions, errors


def check_sources(questions: list[dict]) -> list[str]:
    """Every source must exist in the canonical KB, or the set is stale."""
    errors: list[str] = []
    sections = {path.name: section_names(path) for path in kb_documents(settings.kb_dir)}
    sections["plans.json"] = ["Hotela Dine", "Hotela Suite", "Hotela Stay", "comparison"]
    for item in questions:
        for source in item.get("sources") or []:
            file_name, section = source.get("file"), source.get("section")
            if file_name not in sections:
                errors.append(f"{item['id']}: kb file '{file_name}' is not an indexed knowledge file")
            elif section not in sections[file_name]:
                errors.append(f"{item['id']}: section '{section}' is not in {file_name}")
    return errors


def expected_sources(item: dict) -> list[tuple[str, str]]:
    return [(source["file"], source["section"]) for source in item.get("sources") or []]


def fact_present(fact, text: str) -> bool:
    alternatives = fact if isinstance(fact, list) else [fact]
    return any(str(option).lower() in text for option in alternatives)


# --------------------------------------------------------------------------- #
# retrieval scoring
# --------------------------------------------------------------------------- #
def section_matches(chunk_section: str, expected: str) -> bool:
    return expected == chunk_section or expected in [part.strip() for part in chunk_section.split(">")]


def score_retrieval(question: str, expected: list[tuple[str, str]], k: int, collection, embedder, rewrite) -> tuple[list[RetrievedChunk], float, dict]:
    query = question
    if rewrite is not None:
        query = rewrite(question)
    started = time.perf_counter()
    hits = retrieve(collection, embedder, query, k, settings.min_similarity)
    elapsed = (time.perf_counter() - started) * 1000
    ranks = []
    for file_name, section in expected:
        rank = next(
            (index for index, hit in enumerate(hits, 1) if hit.metadata.get("file") == file_name and section_matches(str(hit.metadata.get("section", "")), section)),
            None,
        )
        ranks.append(rank)
    found = [rank for rank in ranks if rank]
    result = {
        "found": found,
        "ranks": ranks,
        "all_found_at_k": len(found) == len(ranks) if ranks else False,
        "any_found_at_k": bool(found),
        "first_rank": min(found) if found else None,
    }
    return hits, elapsed, result


# --------------------------------------------------------------------------- #
# generation scoring
# --------------------------------------------------------------------------- #
def run_with_deadline(call, timeout: float):
    """Run a blocking call in a daemon thread so a hung request cannot hang the run."""
    box: dict = {}

    def worker() -> None:
        try:
            box["value"] = call()
        except BaseException as error:  # surfaced to the caller
            box["error"] = error

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"no answer within {timeout:.0f}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def parse_sse(text: str) -> tuple[str, list[str]]:
    answer_parts: list[str] = []
    actions: list[str] = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        try:
            event = json.loads(line[6:])
        except json.JSONDecodeError:
            continue
        if event.get("type") == "token":
            answer_parts.append(str(event.get("value", "")))
        elif event.get("type") == "action":
            actions.append(str(event.get("value", "")))
    return "".join(answer_parts), actions


def language_ok(text: str, language: str) -> bool:
    lowered = text.lower()
    if language == "en":
        return True
    markers = LANGUAGE_MARKERS[language]
    if language == "ur":
        return sum(1 for marker in markers if marker in text) >= 2
    return sum(1 for word in lowered.split() if word.strip(".,!?") in markers) >= 2


def unsupported_numbers(answer: str, context: str) -> list[str]:
    allowed = {number.replace(",", "") for number in NUMBER.findall(context)}
    return [number for number in NUMBER.findall(answer) if number.replace(",", "") not in allowed]


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", default=str(QUESTIONS))
    parser.add_argument("--baseline", default=str(BASELINE))
    parser.add_argument("--out", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--k", type=int, default=settings.top_k)
    parser.add_argument("--tolerance", type=float, default=0.0, help="allowed regression before exit 1")
    parser.add_argument("--question-timeout", type=float, default=90.0)
    parser.add_argument("--no-generation", action="store_true", help="retrieval metrics only")
    parser.add_argument("--no-fallback", action="store_true", help="skip the degraded-path measurement")
    parser.add_argument("--require-generation", action="store_true", help="exit 3 if the provider is unavailable")
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--rewrite", action="store_true", help="rewrite the query with the LLM before retrieval")
    args = parser.parse_args()

    questions, errors = load_questions(Path(args.questions))
    errors += check_sources(questions)
    if errors:
        print("EVAL SET INVALID:")
        for error in errors:
            print(f"  - {error}")
        return 2
    if args.limit:
        questions = questions[: args.limit]

    info = collection_info(settings)
    if not info.get("exists"):
        print("EVAL SETUP FAILED: no Chroma collection; run backend/scripts/build_index.py")
        return 2

    embedder = create_embedder(settings.embedding_provider, settings.embedding_model, settings.gemini_api_key)
    collection = load_collection(settings, embedder)

    rewrite = None
    llm = None
    if args.rewrite or not args.no_generation:
        from app.llm.client import GeminiLLMClient

        llm = GeminiLLMClient(settings.gemini_api_key, settings.llm_model, settings.llm_timeout_seconds)
    if args.rewrite and llm is not None:
        rewrite = lambda text: llm.rewrite_query(text, [])  # noqa: E731

    # ---- retrieval half ---------------------------------------------------- #
    scored: list[dict] = []
    reciprocal: list[float] = []
    hit_1 = hit_k = idk_scored = idk_hits = multi_step = multi_step_hits = 0
    latencies: list[float] = []
    for item in questions:
        expected = expected_sources(item)
        if not expected:
            continue
        hits, elapsed, result = score_retrieval(item["question"], expected, args.k, collection, embedder, rewrite)
        latencies.append(elapsed)
        item["_hits"] = hits
        item["_retrieval"] = result
        require_all = item.get("require_all", item.get("kind") == "multi-step")
        passed = result["all_found_at_k"] if require_all else result["any_found_at_k"]
        scored.append(item)
        if passed:
            hit_k += 1
        if result["first_rank"] == 1:
            hit_1 += 1
        # Standard MRR: a miss contributes zero, so the number is comparable between runs.
        reciprocal.append(1 / result["first_rank"] if result["first_rank"] else 0.0)
        if item.get("kind") == "multi-step":
            multi_step += 1
            multi_step_hits += int(passed)
        if item.get("expect") == "handoff":
            # Only questions whose section documents the gap can be scored here;
            # a question nothing in the KB covers has nothing to retrieve.
            idk_scored += 1
            idk_hits += int(result["any_found_at_k"])

    total_scored = len(scored)
    retrieval = {
        "questions_scored": total_scored,
        "k": args.k,
        "hit_1": round(hit_1 / total_scored, 4) if total_scored else 0.0,
        "hit_k": round(hit_k / total_scored, 4) if total_scored else 0.0,
        "mrr": round(statistics.fmean(reciprocal), 4) if reciprocal else 0.0,
        "misses": total_scored - hit_k,
        "multi_step_questions": multi_step,
        "multi_step_hit_k": round(multi_step_hits / multi_step, 4) if multi_step else None,
        "idk_context_hit_k": round(idk_hits / idk_scored, 4) if idk_scored else None,
        "idk_questions": idk_scored,
        "latency_p50_ms": round(statistics.median(latencies), 1) if latencies else None,
        "latency_p95_ms": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 1) if latencies else None,
        "rewrite_enabled": bool(rewrite),
    }

    # ---- generation half ---------------------------------------------------- #
    generation: dict = {"measured": False, "reason": ""}
    if args.no_generation:
        generation["reason"] = "disabled with --no-generation"
    elif llm is None:
        generation["reason"] = "no LLM client"
    else:
        ready, reason = run_with_deadline(llm.preflight, settings.llm_timeout_seconds + 5)
        if not ready:
            generation["reason"] = f"provider unavailable ({reason})"
        else:
            generation.update(run_generation(questions, args, embedder, collection))
            generation["measured"] = True
            generation["preflight"] = reason

    # ---- fallback half ----------------------------------------------------- #
    # The degraded path is always measured: a provider outage is the normal
    # case for this deployment, and it must not be allowed to answer wrongly.
    fallback: dict = {"measured": False, "reason": ""}
    if args.no_fallback:
        fallback["reason"] = "disabled with --no-fallback"
    else:
        fallback.update(run_generation(questions, args, embedder, collection, llm=FailingLLM(), label="_fallback"))
        fallback["measured"] = True

    # ---- report ------------------------------------------------------------- #
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "questions": len(questions),
        "kb_version": info.get("kb_version"),
        "kb_chunks": info.get("count"),
        "token_estimator": token_estimator(),
        "embedding_provider": embedder.provider,
        "embedding_model": embedder.model,
        "top_k": settings.top_k,
        "min_similarity": settings.min_similarity,
        "llm_timeout_seconds": settings.llm_timeout_seconds,
        "question_timeout_seconds": args.question_timeout,
        "retrieval_config": {
            "top_k": settings.top_k,
            "min_similarity": settings.min_similarity,
            "candidate_k": settings.candidate_k,
            "hybrid": settings.retrieval_hybrid,
            "hybrid_rrf_k": settings.retrieval_hybrid_rrf_k,
            "script_boost": settings.retrieval_script_boost,
            "dedupe": settings.retrieval_dedupe,
            "answer_min_similarity": settings.retrieval_answer_min_similarity,
        },
        "retrieval": retrieval,
        "generation": generation,
        "fallback": fallback,
        "per_question": [
            {
                "id": item["id"],
                "kind": item["kind"],
                "expect": item["expect"],
                "sources": [f"{file_name} > {section}" for file_name, section in expected_sources(item)],
                "retrieved": [
                    {"file": hit.metadata.get("file"), "section": hit.metadata.get("section"), "similarity": round(hit.similarity, 3)}
                    for hit in item.get("_hits", [])
                ],
                "ranks": (item.get("_retrieval") or {}).get("ranks"),
                "generation": item.get("_generation") or {},
                "fallback": item.get("_fallback") or {},
                **({"language_ok": item["_language_ok"]} if "_language_ok" in item else {}),
                **({"fallback_language_ok": item["_fallback_language_ok"]} if "_fallback_language_ok" in item else {}),
            }
            for item in questions
        ],
    }
    print_summary(results)
    out_path = Path(args.out) if args.out else RESULTS_DIR / f"eval-{results['generated_at'].replace(':', '').replace('-', '')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nresults written to {display_path(out_path)}")

    if args.update_baseline:
        baseline_path = Path(args.baseline)
        baseline = {
            "updated_at": results["generated_at"],
            "questions": results["questions"],
            "kb_version": results["kb_version"],
            "kb_chunks": results["kb_chunks"],
            "token_estimator": results["token_estimator"],
            "embedding_provider": results["embedding_provider"],
            "embedding_model": results["embedding_model"],
            "top_k": results["top_k"],
            "min_similarity": results["min_similarity"],
            "retrieval_config": results["retrieval_config"],
            "retrieval": retrieval,
            "generation": {"measured": generation.get("measured", False), "reason": generation.get("reason", "")},
            "fallback": fallback,
        }
        baseline_path.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        print(f"baseline written to {display_path(baseline_path)}")

    if args.require_generation and not generation.get("measured"):
        print(f"GENERATION REQUIRED BUT NOT MEASURED: {generation.get('reason')}")
        return 3

    baseline_path = Path(args.baseline)
    if baseline_path.exists() and not args.update_baseline:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        regressions = []
        for key in METRIC_KEYS:
            before, after = baseline.get("retrieval", {}).get(key), retrieval.get(key)
            if before is None or after is None:
                continue
            if after < before - args.tolerance:
                regressions.append(f"{key}: {before} -> {after} (tolerance {args.tolerance})")
        if baseline.get("top_k") != retrieval["k"]:
            regressions.append(f"top_k changed: {baseline.get('top_k')} -> {retrieval['k']}; baseline and run are not comparable")
        # The degraded path must not get worse: a visitor with the provider
        # down must still get a grounded answer.
        for key in FALLBACK_METRIC_KEYS:
            before, after = baseline.get("fallback", {}).get(key), fallback.get(key)
            if before is None or after is None:
                continue
            if after < before - args.tolerance:
                regressions.append(f"fallback.{key}: {before} -> {after} (tolerance {args.tolerance})")
        before_unsupported = baseline.get("fallback", {}).get("unsupported_number_answers")
        after_unsupported = fallback.get("unsupported_number_answers")
        if before_unsupported is not None and after_unsupported is not None and after_unsupported > before_unsupported:
            regressions.append(f"fallback.unsupported_number_answers: {before_unsupported} -> {after_unsupported}")
        if regressions:
            print("\nREGRESSION AGAINST BASELINE:")
            for line in regressions:
                print(f"  - {line}")
            return 1
        print("\nno retrieval or fallback regression against the baseline")
    return 0


class FailingLLM:
    """A provider that is down.

    Used to measure the degraded path: the service must still answer from the
    knowledge base, in the visitor's language, without inventing anything.
    """

    model = "forced-failure"

    def rewrite_query(self, message: str, history: list[dict]) -> str:
        return message

    def stream_answer(self, message, context, core_facts, history):
        raise RuntimeError("provider unavailable (forced failure for the fallback measurement)")

    def preflight(self) -> tuple[bool, str]:
        return False, "provider forced to fail for the fallback measurement"


def run_generation(questions: list[dict], args, embedder, collection, llm=None, label: str = "_generation") -> dict:
    """Drive the real /api/chat SSE surface and score the answers.

    `llm` replaces the provider the app would otherwise use, which is how the
    fallback half forces the degraded path through the same API.
    """
    from fastapi.testclient import TestClient

    import app.main as main_module
    from app.main import app, limiter

    from app.chat.service import ChatService

    # The plan table and contact lines the service itself puts in the prompt, so
    # faithfulness is checked against exactly the facts the model was given.
    core_facts = ChatService(settings, collection, embedder, None)._core_facts()
    context_by_id = {
        item["id"]: "\n\n".join(hit.text for hit in item.get("_hits", [])) for item in questions
    }

    counts = {key: 0 for key in ("answer", "answer_correct", "grounded", "unsupported", "handoff", "handoff_correct", "redirect", "redirect_correct", "smalltalk", "smalltalk_correct", "request_errors", "language_checked", "language_correct")}
    limiter.enabled = False

    original_build = main_module.build_service
    if llm is not None:
        main_module.build_service = lambda: ChatService(settings, collection, embedder, llm)
    try:
        with TestClient(app) as client:
            for item in questions:
                expect = item["expect"]
                started = time.perf_counter()
                try:
                    response = run_with_deadline(
                        lambda item=item: client.post(
                            "/api/chat",
                            json={"session_id": f"eval-{item['id']}", "message": item["question"], "history": []},
                        ),
                        args.question_timeout,
                    )
                    answer, actions = parse_sse(response.text)
                except Exception as error:
                    counts["request_errors"] += 1
                    item[label] = {"answer": "", "error": f"{type(error).__name__}: {error}", "seconds": round(time.perf_counter() - started, 2)}
                    continue
                lowered = answer.lower()
                context = (context_by_id.get(item["id"], "") + "\n" + core_facts).lower()
                entry: dict = {
                    "answer": answer[:400],
                    "actions": actions,
                    "seconds": round(time.perf_counter() - started, 2),
                }
                if expect == "answer":
                    facts = item.get("answer_facts") or []
                    matched = [fact for fact in facts if fact_present(fact, lowered)]
                    entry["facts_matched"] = len(matched)
                    entry["facts_total"] = len(facts)
                    counts["answer"] += 1
                    if len(matched) == len(facts) and facts:
                        counts["answer_correct"] += 1
                    # Faithful means: the answer states at least one checked fact and every
                    # fact it does state is traceable to the context. An answer that matched
                    # no checked fact cannot be called faithful - it measured nothing.
                    if matched and all(fact_present(fact, context) for fact in matched):
                        counts["grounded"] += 1
                    unsupported = unsupported_numbers(answer, context)
                    if unsupported:
                        counts["unsupported"] += 1
                        entry["unsupported_numbers"] = unsupported
                    language = item.get("language", "en")
                    language_key = "_language_ok" if label == "_generation" else "_fallback_language_ok"
                    item[language_key] = language_ok(answer, language)
                    counts["language_checked"] += 1
                    counts["language_correct"] += int(item[language_key])
                elif expect == "handoff":
                    counts["handoff"] += 1
                    if any(marker in lowered for marker in ANSWER_MARKERS["handoff"]) or "handoff" in actions:
                        counts["handoff_correct"] += 1
                elif expect == "redirect":
                    counts["redirect"] += 1
                    if "help with hotela" in lowered:
                        counts["redirect_correct"] += 1
                elif expect == "smalltalk":
                    counts["smalltalk"] += 1
                    if answer.strip() and not any(marker in lowered for marker in ("not sure", "hotelaapp@gmail.com")):
                        counts["smalltalk_correct"] += 1
                item[label] = entry
    finally:
        main_module.build_service = original_build

    def rate(hit: str, total: str) -> float | None:
        return round(counts[hit] / counts[total], 4) if counts[total] else None

    return {
        "answers_scored": counts["answer"],
        "answer_correct": counts["answer_correct"],
        "answer_correct_rate": rate("answer_correct", "answer"),
        "faithful": counts["grounded"],
        "faithfulness_rate": rate("grounded", "answer"),
        "unsupported_number_answers": counts["unsupported"],
        "handoff_questions": counts["handoff"],
        "handoff_correct": counts["handoff_correct"],
        "handoff_rate": rate("handoff_correct", "handoff"),
        "redirect_questions": counts["redirect"],
        "redirect_correct": counts["redirect_correct"],
        "redirect_rate": rate("redirect_correct", "redirect"),
        "smalltalk_questions": counts["smalltalk"],
        "smalltalk_correct": counts["smalltalk_correct"],
        "smalltalk_rate": rate("smalltalk_correct", "smalltalk"),
        "language_checked": counts["language_checked"],
        "language_correct": counts["language_correct"],
        "language_rate": rate("language_correct", "language_checked"),
        "request_errors": counts["request_errors"],
    }


def display_path(path: Path) -> str:
    """Relative to the repository when it is inside it, absolute otherwise."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def print_summary(results: dict) -> None:
    retrieval = results["retrieval"]
    print("=" * 72)
    print("HOTELA ASSISTANT EVALUATION")
    print("=" * 72)
    print(f"questions: {results['questions']}   scored for retrieval: {retrieval['questions_scored']}   k={retrieval['k']}")
    print(f"kb_version: {results['kb_version']}   chunks: {results['kb_chunks']}   estimator: {results['token_estimator']}")
    print(f"embeddings: {results['embedding_provider']}:{results['embedding_model']}")
    config = results.get("retrieval_config") or {}
    if config:
        print(
            f"retrieval config: k={config.get('top_k')} min_similarity={config.get('min_similarity')} "
            f"candidate_k={config.get('candidate_k')} hybrid={config.get('hybrid')} "
            f"rrf_k={config.get('hybrid_rrf_k')} script_boost={config.get('script_boost')} dedupe={config.get('dedupe')}"
        )
    print()
    print("RETRIEVAL (local, measured)")
    print(f"  hit@1                : {retrieval['hit_1']:.3f}")
    print(f"  hit@{retrieval['k']}                : {retrieval['hit_k']:.3f}  ({retrieval['misses']} misses)")
    print(f"  MRR                  : {retrieval['mrr']:.3f}  (misses count as zero)")
    if retrieval["multi_step_hit_k"] is not None:
        print(f"  multi-step hit@{retrieval['k']}     : {retrieval['multi_step_hit_k']:.3f}  ({retrieval['multi_step_questions']} questions needing two sections)")
    if retrieval["idk_context_hit_k"] is not None:
        print(f"  IDK context hit@{retrieval['k']}    : {retrieval['idk_context_hit_k']:.3f}  ({retrieval['idk_questions']} 'not confirmed' questions)")
    print(f"  retrieval latency    : p50 {retrieval['latency_p50_ms']} ms, p95 {retrieval['latency_p95_ms']} ms")
    print(f"  query rewrite        : {'on' if retrieval['rewrite_enabled'] else 'off (raw question, provider-independent)'}")
    print()
    generation = results["generation"]
    if generation.get("measured"):
        print("GENERATION (provider, measured)")
        print(f"  answer correct       : {generation['answer_correct']}/{generation['answers_scored']} = {generation['answer_correct_rate']}")
        print(f"  faithfulness         : {generation['faithful']}/{generation['answers_scored']} = {generation['faithfulness_rate']}")
        print(f"  unsupported numbers  : {generation['unsupported_number_answers']} answers")
        print(f"  handoff correct      : {generation['handoff_correct']}/{generation['handoff_questions']} = {generation['handoff_rate']}")
        print(f"  redirect correct     : {generation['redirect_correct']}/{generation['redirect_questions']} = {generation['redirect_rate']}")
        print(f"  small talk correct   : {generation['smalltalk_correct']}/{generation['smalltalk_questions']} = {generation['smalltalk_rate']}")
        print(f"  language correct     : {generation['language_correct']}/{generation['language_checked']} = {generation['language_rate']}")
        print(f"  request errors       : {generation['request_errors']} (per-question deadline {results.get('question_timeout_seconds')}s)")
    else:
        print("GENERATION: NOT MEASURED")
        print(f"  reason: {generation.get('reason')}")
        print("  answer correctness, faithfulness, handoff/redirect behaviour and language stay")
        print("  unmeasured until a provider answers; retrieval numbers above are unaffected.")
    print()
    fallback = results.get("fallback") or {}
    if fallback.get("measured"):
        print("FALLBACK (provider forced to fail, measured)")
        print(f"  answer correct       : {fallback['answer_correct']}/{fallback['answers_scored']} = {fallback['answer_correct_rate']}")
        print(f"  faithfulness         : {fallback['faithful']}/{fallback['answers_scored']} = {fallback['faithfulness_rate']}")
        print(f"  unsupported numbers  : {fallback['unsupported_number_answers']} answers")
        print(f"  handoff correct      : {fallback['handoff_correct']}/{fallback['handoff_questions']} = {fallback['handoff_rate']}")
        print(f"  redirect correct     : {fallback['redirect_correct']}/{fallback['redirect_questions']} = {fallback['redirect_rate']}")
        print(f"  small talk correct   : {fallback['smalltalk_correct']}/{fallback['smalltalk_questions']} = {fallback['smalltalk_rate']}")
        print(f"  language correct     : {fallback['language_correct']}/{fallback['language_checked']} = {fallback['language_rate']}")
        print(f"  request errors       : {fallback['request_errors']}")
    else:
        print("FALLBACK: NOT MEASURED")
        print(f"  reason: {fallback.get('reason')}")
    print()


if __name__ == "__main__":
    raise SystemExit(main())
