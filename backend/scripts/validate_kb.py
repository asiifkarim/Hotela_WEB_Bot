"""Validate the knowledge base before it is indexed.

Layout rule: `kb/` holds exactly one canonical file per topic, named after its
topic (`kb/bookings.md` carries `topic: bookings`). The indexed set is every
top-level `kb/*.md` that declares the six front-matter keys below; subfolders
(`kb/archive/`) and the registers (`kb/GAPS.md`, `kb/README.md`) are never
indexed, which is enforced here rather than trusted.

Checks:
- every required topic file exists, and every indexed file's `topic` matches its file name
- front matter carries title, topic, source, last_updated, version, audience with sane values
- no TODO/CONFLICT maintainer notes leak into indexed prose
- no 60-character-plus line is repeated across two indexed files (the duplicate-content guard)
- plans.json stays the single source for plan names, prices, billing period and plan features
- kb/GAPS.md exists and carries no front matter, so it can never be retrieved
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KB = ROOT / "kb"
PLANS = KB / "plans.json"
GAPS = KB / "GAPS.md"
REQUIRED_FRONT_MATTER = ("title", "topic", "source", "last_updated", "version", "audience")
REQUIRED_TOPICS = (
    "app_how_to",
    "bookings",
    "customers",
    "faq",
    "finances",
    "invoices",
    "policies",
    "rooms_pricing",
)
OPTIONAL_TOPICS = ("glossary",)
NON_KB_FILES = ("GAPS.md", "README.md")
AUDIENCES = ("visitor", "maintainer", "staff")
MIN_SHARED_LINE = 60


def parse_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith(("---\n", "---\r\n")):
        raise ValueError(f"{path}: missing front matter")
    end = text.find("\n---", 4)
    if end < 0:
        raise ValueError(f"{path}: unterminated front matter")
    metadata = yaml.safe_load(text[text.index("\n") + 1:end]) or {}
    body_start = text.find("\n", end + 1)
    body = text[body_start + 1:].strip() if body_start >= 0 else ""
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: front matter must be a mapping")
    missing = [key for key in REQUIRED_FRONT_MATTER if not metadata.get(key)]
    if missing:
        raise ValueError(f"{path}: front matter is missing {', '.join(missing)}")
    if not body:
        raise ValueError(f"{path}: body is empty")
    return metadata, body


def validate_plans() -> None:
    data = json.loads(PLANS.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("currency"), str) or not isinstance(data.get("plans"), list):
        raise ValueError("plans.json: expected currency and plans")
    keys = {"name", "price", "duration_months", "billing_note", "features"}
    for plan in data["plans"]:
        if set(plan) != keys or not isinstance(plan["name"], str) or not isinstance(plan["features"], list):
            raise ValueError("plans.json: invalid plan schema")


def indexed_files() -> list[Path]:
    """Top-level kb markdown files that are meant to be indexed."""
    return [path for path in sorted(KB.glob("*.md")) if path.name not in NON_KB_FILES]


def main() -> int:
    errors: list[str] = []
    files = indexed_files()
    names = {path.name for path in files}

    stems = {path.stem for path in files}
    for topic in REQUIRED_TOPICS:
        if f"{topic}.md" not in names:
            errors.append(f"missing canonical file {KB / (topic + '.md')}")
    for stem in sorted(stems - set(REQUIRED_TOPICS) - set(OPTIONAL_TOPICS)):
        errors.append(f"{KB / (stem + '.md')}: unknown topic; add it to REQUIRED_TOPICS/OPTIONAL_TOPICS or name the file after its topic")
    if not GAPS.exists():
        errors.append(f"missing {GAPS}; claims that need a human decision must be recorded there")

    topics: dict[str, str] = {}
    bodies: dict[str, str] = {}
    total_chars = 0
    todo = 0
    conflict = 0

    for path in files:
        try:
            metadata, body = parse_markdown(path)
            topic = str(metadata["topic"])
            if path.stem != topic:
                errors.append(f"{path}: topic '{topic}' must equal the file name '{path.stem}'")
            if topic in topics:
                errors.append(f"{path}: topic '{topic}' is already used by {topics[topic]}; keep one canonical file per topic")
            else:
                topics[topic] = path.name
            audience = str(metadata["audience"])
            if audience not in AUDIENCES:
                errors.append(f"{path}: audience '{audience}' must be one of {', '.join(AUDIENCES)}")
            try:
                date.fromisoformat(str(metadata["last_updated"]))
            except ValueError:
                errors.append(f"{path}: last_updated '{metadata['last_updated']}' is not an ISO date")
            if not isinstance(metadata["version"], int) or metadata["version"] < 1:
                errors.append(f"{path}: version must be a positive integer")
            if not metadata.get("source_urls"):
                errors.append(f"{path}: add source_urls so a reviewer can re-check the claims")
            bodies[path.name] = body
            total_chars += len(body)
            todo += body.count("TODO")
            conflict += body.count("CONFLICT")
            if "lorem ipsum" in body.lower():
                errors.append(f"{path}: contains lorem ipsum")
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(str(exc))

    if todo or conflict:
        errors.append(f"indexed files contain {todo} TODO and {conflict} CONFLICT notes; move open questions to kb/GAPS.md so they are not indexed")

    seen_lines: dict[str, str] = {}
    for name, body in bodies.items():
        for line in body.splitlines():
            normalized = " ".join(line.split()).lower()
            if len(normalized) < MIN_SHARED_LINE or normalized.startswith(("|", "---")):
                continue
            if normalized in seen_lines and seen_lines[normalized] != name:
                errors.append(f"{name} and {seen_lines[normalized]} repeat the same line: '{normalized[:80]}...'")
            seen_lines.setdefault(normalized, name)

    try:
        validate_plans()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    if GAPS.exists():
        gaps_text = GAPS.read_text(encoding="utf-8")
        if gaps_text.startswith(("---\n", "---\r\n")):
            errors.append(f"{GAPS}: must not carry front matter, otherwise it becomes an indexed document")
    total_chars += len(GAPS.read_text(encoding="utf-8")) if GAPS.exists() else 0

    chunks = 0
    estimator = "unknown"
    try:
        sys.path.insert(0, str(ROOT / "backend"))
        from app.rag.chunker import load_all_chunks, token_estimator  # imported here so the check reports the real index size

        estimator = token_estimator()
        chunks = len(load_all_chunks(KB, "validate"))
    except Exception as exc:
        errors.append(f"chunk check failed: {type(exc).__name__}: {exc}")

    tokens = total_chars // 4
    print(f"Canonical KB files: {len(files)} ({len(topics)} topics)")
    print(f"Indexed chunks: {chunks} (sized with {estimator})")
    print(f"KB size estimate: {tokens} tokens (chars/4, registers included; build_index.py prints the tiktoken count)")
    print(f"TODO markers in indexed files: {todo}")
    print(f"CONFLICT markers in indexed files: {conflict}")
    print(f"Recommendation: {'full-prompt mode' if tokens < 30000 else 'RAG'}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
