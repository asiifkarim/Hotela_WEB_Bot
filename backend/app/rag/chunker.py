from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Chunk:
    text: str
    metadata: dict[str, Any]
    chunk_id: str


def token_estimator() -> str:
    """Name of the estimator that sizes chunks.

    The chunk boundaries, and therefore the chunk count, depend on this. It is
    reported by the build and the validator so a count from an environment
    without tiktoken is never mistaken for the indexed count.
    """
    try:
        import tiktoken  # noqa: F401

        return "tiktoken:cl100k_base"
    except Exception:
        return "chars/4 fallback (tiktoken is not installed)"


def estimate_tokens(text: str) -> int:
    if token_estimator().startswith("tiktoken"):
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    return max(1, len(text) // 4)


REQUIRED_FRONT_MATTER = ("title", "topic", "source", "last_updated", "version", "audience")
NON_KB_FILES = frozenset({"GAPS.md", "README.md"})


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\r\n") and not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    body_start = text.find("\n", end + 1)
    if body_start < 0:
        return {}, ""
    return yaml.safe_load(text[text.index("\n") + 1:end]) or {}, text[body_start + 1:]


def is_kb_document(path: Path) -> bool:
    """True when a top-level kb file declares the front matter the index expects."""
    if path.name.startswith("_") or path.name in NON_KB_FILES:
        return False
    metadata, _body = parse_front_matter(path.read_text(encoding="utf-8"))
    return all(metadata.get(key) for key in REQUIRED_FRONT_MATTER)


def kb_documents(kb_dir: Path) -> list[Path]:
    """Canonical knowledge files: one per topic, directly under kb/.

    Subdirectories (kb/archive, and any legacy folder) are never indexed, and
    neither are the registers that carry no front matter.
    """
    return [path for path in sorted(kb_dir.glob("*.md")) if is_kb_document(path)]


def _sections(body: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^(#{2,3})\s+(.+?)\s*$", body, re.MULTILINE))
    if not matches:
        return [("General", body.strip())]
    result: list[tuple[str, str]] = []
    path: list[str] = []
    for index, match in enumerate(matches):
        level = len(match.group(1)) - 2
        heading = match.group(2).strip()
        if level == 0:
            path = [heading]
        else:
            path = path[:1] + [heading]
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        content = body[start:end].strip()
        if content:
            result.append((" > ".join(path), content))
    return result


def _is_only_todo(text: str) -> bool:
    remaining = re.sub(r"TODO:\s*not found on website[^\n]*", "", text, flags=re.I)
    return not re.sub(r"[-*:\s]", "", remaining).strip()


def _base_metadata(metadata: dict[str, Any], file_name: str, section: str, index: int, kb_version: str) -> dict[str, Any]:
    source_urls = metadata.get("source_urls") or metadata.get("source") or []
    if isinstance(source_urls, str):
        source_urls = [source_urls]
    return {
        "file": file_name,
        "topic": metadata.get("topic", Path(file_name).stem),
        "section": section,
        "source_urls": [str(url) for url in source_urls],
        "audience": str(metadata.get("audience", "visitor")),
        "last_updated": str(metadata.get("last_updated", "")),
        "lang": "en",
        "chunk_id": f"{file_name}:{section}:{index}",
        "kb_version": kb_version,
    }


def _overlap_tail(text: str, overlap_tokens: int) -> str:
    """The trailing sentences of a chunk that are repeated in the next one."""
    if overlap_tokens <= 0:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    tail: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        count = estimate_tokens(sentence)
        if total + count > overlap_tokens:
            break
        tail.insert(0, sentence)
        total += count
    return " ".join(tail).strip()


def _make_chunks(
    file_name: str,
    metadata: dict[str, Any],
    sections: list[tuple[str, str]],
    kb_version: str,
    one_per_section: bool = False,
    *,
    max_tokens: int = 400,
    min_tokens: int = 200,
    overlap_tokens: int = 0,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    pending: list[tuple[str, str]] = []
    pending_tokens = 0
    index = 0
    carry = ""

    def flush() -> None:
        nonlocal index, pending, pending_tokens, carry
        if not pending:
            return
        section = " > ".join(item[0] for item in pending)
        content = "\n\n".join(item[1] for item in pending)
        if carry:
            content = f"{carry}\n\n{content}"
        text = f"{section}:\n{content}"
        chunk_id = f"{file_name}:{section}:{index}"
        chunks.append(Chunk(text, _base_metadata(metadata, file_name, section, index, kb_version), chunk_id))
        index += 1
        pending = []
        pending_tokens = 0
        carry = _overlap_tail(content, overlap_tokens)

    for section, content in sections:
        if _is_only_todo(content):
            continue
        if one_per_section and pending:
            flush()
        tokens = estimate_tokens(content)
        if pending and pending_tokens + tokens > max_tokens:
            flush()
        pending.append((section, content))
        pending_tokens += tokens
        if one_per_section or pending_tokens >= min_tokens:
            flush()
    flush()
    return chunks


def section_names(path: Path) -> list[str]:
    """Heading path of every section in a knowledge file.

    The evaluator checks its source references against this, so a question can
    never point at a section that no longer exists.
    """
    _metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
    return [section for section, _content in _sections(body)]


def section_text(path: Path, heading: str) -> str:
    """Return one question-or-section body from a knowledge file, without its heading.

    Used where the prompt needs a single curated section (contact details, for
    example) instead of a whole file. Returns "" when the heading is absent.
    """
    if not path.exists():
        return ""
    _metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
    wanted = heading.strip().lower()
    for section, content in _sections(body):
        if section.strip().lower() == wanted:
            return content
    return ""


def chunk_markdown(
    path: Path,
    kb_version: str,
    *,
    max_tokens: int = 400,
    min_tokens: int = 200,
    overlap_tokens: int = 0,
) -> list[Chunk]:
    metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
    return _make_chunks(
        path.name,
        metadata,
        _sections(body),
        kb_version,
        "faq" in path.stem.lower(),
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        overlap_tokens=overlap_tokens,
    )


def chunk_plans(path: Path, kb_version: str) -> list[Chunk]:
    data = json.loads(path.read_text(encoding="utf-8"))
    chunks: list[Chunk] = []
    for index, plan in enumerate(data.get("plans", [])):
        text = (
            f"Plan: {plan['name']}\nPrice: {data['currency']} {plan['price']}\n"
            f"Duration: {plan['duration_months']} months\nBilling: {plan['billing_note']}\n"
            f"Features: {', '.join(plan['features'])}"
        )
        metadata = {"file": path.name, "topic": "plans", "section": plan["name"], "source_urls": ["kb/plans.json"], "audience": "visitor", "last_updated": "", "lang": "en", "chunk_id": f"{path.name}:{plan['name']}:{index}", "kb_version": kb_version}
        chunks.append(Chunk(text, metadata, metadata["chunk_id"]))
    rows = ["Plans comparison:"]
    for plan in data.get("plans", []):
        rows.append(f"- {plan['name']}: {data['currency']} {plan['price']} for {plan['duration_months']} months; {plan['billing_note']}; features: {', '.join(plan['features'])}")
    metadata = {"file": path.name, "topic": "plans", "section": "comparison", "source_urls": ["kb/plans.json"], "audience": "visitor", "last_updated": "", "lang": "en", "chunk_id": f"{path.name}:comparison:0", "kb_version": kb_version}
    chunks.append(Chunk("\n".join(rows), metadata, metadata["chunk_id"]))
    return chunks


def load_all_chunks(
    kb_dir: Path,
    kb_version: str,
    *,
    max_tokens: int = 400,
    min_tokens: int = 200,
    overlap_tokens: int = 0,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in kb_documents(kb_dir):
        chunks.extend(
            chunk_markdown(
                path,
                kb_version,
                max_tokens=max_tokens,
                min_tokens=min_tokens,
                overlap_tokens=overlap_tokens,
            )
        )
    plans = kb_dir / "plans.json"
    if plans.exists():
        chunks.extend(chunk_plans(plans, kb_version))
    return chunks
