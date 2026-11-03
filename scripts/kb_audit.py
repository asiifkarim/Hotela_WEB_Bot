"""Audit the knowledge base: hashes, exact duplicates and near duplicates.

Usage:
    python scripts/kb_audit.py                # markdown report for every file under kb/
    python scripts/kb_audit.py --root kb      # audit another directory
    python scripts/kb_audit.py --threshold 0.3

Stdlib only, so it runs without the application dependencies. The report is
markdown on stdout; redirect it to a file to keep a snapshot of a run.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import re
from pathlib import Path

FRONT_MATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.S)
WORD = re.compile(r"[a-z0-9]+")
SHINGLE_SIZE = 5
MIN_SHARED_WORDS = 12


def read(path: Path) -> tuple[str, dict[str, str], str]:
    """Return (raw text, front matter mapping, body)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    match = FRONT_MATTER.match(text)
    fields: dict[str, str] = {}
    body = text
    if match:
        body = text[match.end():]
        for line in match.group(1).splitlines():
            key, _, value = line.partition(":")
            if value.strip():
                fields[key.strip()] = value.strip()
    return text, fields, body


def words(body: str) -> list[str]:
    cleaned = re.sub(r"[`*_>#|]", " ", body.lower())
    return WORD.findall(cleaned)


def shingles(tokens: list[str], size: int = SHINGLE_SIZE) -> set[tuple[str, ...]]:
    if len(tokens) < size:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def jaccard(left: set, right: set) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def longest_shared_run(left: list[str], right: list[str], cap: int = 120) -> tuple[int, str]:
    """Longest identical word run in two documents (binary search on the run length)."""
    def has(size: int):
        if size <= 0:
            return None
        grams = {tuple(right[i:i + size]) for i in range(len(right) - size + 1)}
        for i in range(len(left) - size + 1):
            gram = tuple(left[i:i + size])
            if gram in grams:
                return gram
        return None

    best, passage = 0, ""
    low, high = 1, min(len(left), len(right), cap)
    while low <= high:
        middle = (low + high) // 2
        found = has(middle)
        if found:
            best, passage = middle, " ".join(found)
            low = middle + 1
        else:
            high = middle - 1
    return best, passage


def normalize(text: str) -> str:
    """Collapse line endings and trailing whitespace so copies compare equal."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n"))


def collected(paths: list[Path]) -> dict[str, dict]:
    files: dict[str, dict] = {}
    for path in paths:
        text, fields, body = read(path)
        tokens = words(body)
        files[path.as_posix()] = {
            "text": text,
            "body": body,
            "fields": fields,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
            "normalized_sha256": hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:12],
            "bytes": len(text.encode("utf-8")),
            "lines": text.count("\n") + 1,
            "words": len(tokens),
            "est_tokens": max(1, len(text) // 4),
            "topic": fields.get("topic", ""),
            "headings": len(re.findall(r"^#{1,3} ", body, re.M)),
            "tokens": set(tokens),
            "shingles": shingles(tokens),
        }
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="kb", help="directory to audit (default: kb)")
    parser.add_argument("--threshold", type=float, default=0.25, help="near-duplicate cutoff")
    parser.add_argument("--exclude", action="append", default=[], help="path prefix to skip, repeatable (e.g. kb/archive)")
    args = parser.parse_args()

    root = Path(args.root)
    excluded = [prefix.rstrip("/") for prefix in args.exclude]
    paths = sorted(
        path for path in root.rglob("*")
        if path.is_file() and not any(path.as_posix().startswith(prefix) for prefix in excluded)
    )
    files = collected(paths)
    keys = list(files)

    print("# Knowledge base audit data")
    print()
    print(f"Root: `{root.as_posix()}`  |  files: {len(files)}  |  "
          f"estimated tokens: {sum(item['est_tokens'] for item in files.values())}")
    print()

    print("## Inventory")
    print()
    print("| File | sha256 | Bytes | Lines | Words | Est. tokens | topic | Headings | Front matter |")
    print("|---|---|---|---|---|---|---|---|---|")
    for key in keys:
        item = files[key]
        has_fm = "yes" if item["fields"] else "no"
        print(f"| `{key}` | `{item['sha256']}` | {item['bytes']} | {item['lines']} | "
              f"{item['words']} | {item['est_tokens']} | {item['topic'] or '-'} | "
              f"{item['headings']} | {has_fm} |")
    print()

    print("## Exact duplicates (identical sha256)")
    print()
    by_hash: dict[str, list[str]] = {}
    for key in keys:
        by_hash.setdefault(files[key]["sha256"], []).append(key)
    groups = [group for group in by_hash.values() if len(group) > 1]
    if not groups:
        print("None.")
    for group in groups:
        print(f"- `{files[group[0]]['sha256']}`: " + ", ".join(f"`{name}`" for name in group))
    print()

    print("## Content duplicates after line-ending normalisation")
    print()
    print("Same text once CRLF/whitespace differences are ignored - the copies a human would call identical.")
    print()
    by_normal: dict[str, list[str]] = {}
    for key in keys:
        by_normal.setdefault(files[key]["normalized_sha256"], []).append(key)
    normal_groups = [group for group in by_normal.values() if len(group) > 1]
    if not normal_groups:
        print("None.")
    for group in normal_groups:
        raw = ", ".join(sorted({files[name]["sha256"] for name in group}))
        print(f"- `{files[group[0]]['normalized_sha256']}` (raw: {raw}): "
              + ", ".join(f"`{name}`" for name in group))
    print()

    print(f"## Near duplicates (similarity >= {args.threshold})")
    print()
    print("Similarity is the higher of token-set Jaccard and 5-word-shingle Jaccard on the body text.")
    print()
    pairs = []
    for left, right in itertools.combinations(keys, 2):
        token_score = jaccard(files[left]["tokens"], files[right]["tokens"])
        shingle_score = jaccard(files[left]["shingles"], files[right]["shingles"])
        score = max(token_score, shingle_score)
        if score >= args.threshold:
            pairs.append((score, token_score, shingle_score, left, right))
    pairs.sort(reverse=True)
    if not pairs:
        print("None.")
    else:
        print("| Similarity | Tokens | Shingles | File A | File B |")
        print("|---|---|---|---|---|")
        for score, token_score, shingle_score, left, right in pairs:
            print(f"| {score:.2f} | {token_score:.2f} | {shingle_score:.2f} | `{left}` | `{right}` |")
    print()

    print(f"## Longest shared passage between files (>= {MIN_SHARED_WORDS} words)")
    print()
    print("A proxy for duplicated claims: the longest identical word run two files share.")
    print()
    shared_runs = []
    for left, right in itertools.combinations(keys, 2):
        size, passage = longest_shared_run(words(files[left]["body"]), words(files[right]["body"]))
        if size >= MIN_SHARED_WORDS:
            shared_runs.append((size, left, right, passage))
    shared_runs.sort(reverse=True)
    if not shared_runs:
        print("None.")
    else:
        print("| Words | File A | File B | Passage |")
        print("|---|---|---|---|")
        for size, left, right, passage in shared_runs:
            print(f"| {size} | `{left}` | `{right}` | {passage} |")
    print()

    print("## Topic collisions (`topic:` in front matter)")
    print()
    by_topic: dict[str, list[str]] = {}
    for key in keys:
        if files[key]["topic"]:
            by_topic.setdefault(files[key]["topic"], []).append(key)
    collisions = {topic: group for topic, group in by_topic.items() if len(group) > 1}
    if not collisions:
        print("None.")
    else:
        for topic, group in sorted(collisions.items()):
            print(f"- `{topic}`: " + ", ".join(f"`{name}`" for name in group))
    print()
    print(f"Distinct topics: {len(by_topic)}  |  files declaring a topic: "
          f"{sum(len(group) for group in by_topic.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
