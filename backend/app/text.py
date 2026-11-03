"""Text helpers shared by the chat service: language detection, redaction, cleanup.

Kept in one place so the service, the retriever and the evaluator agree on what
"Urdu", "Roman Urdu" and "English" mean.
"""

from __future__ import annotations

import re

ARABIC_BLOCK = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")

# Roman Urdu markers: words that almost never appear in ordinary English but are
# the backbone of Roman Urdu. Used only to pick the reply style, never to decide
# whether a fact is true.
ROMAN_URDU_MARKERS = frozenset(
    {
        "hai", "hain", "ka", "ki", "ke", "ko", "mein", "mein", "kya", "koi", "aur",
        "nahi", "nahin", "sir", "madad", "karein", "kare", "karna", "hota", "hoti",
        "haiye", "acha", "theek", "batao", "bata", "shukriya", "assalam", "salam",
        "kitna", "kitni", "kyun", "kahan", "kab", "kaise", "kaisay", "aap", "mujhe",
        "mera", "meri", "hamara", "bataiye", "chahiye", "chalega", "rahe", "rahi",
        "hona", "hota", "karni", "chahiye", "kaisa", "kis",
    }
)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")


def script_of(text: str) -> str:
    """Return "arabic", "latin" or "mixed" for the given text."""
    has_arabic = bool(ARABIC_BLOCK.search(text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "arabic"
    if has_latin:
        return "latin"
    return "none"


def detect_language(text: str) -> str:
    """Return "ur" (Urdu script), "ru" (Roman Urdu) or "en" (English)."""
    if not text or not text.strip():
        return "en"
    if ARABIC_BLOCK.search(text):
        return "ur"
    if roman_urdu_score(text) >= 2:
        return "ru"
    return "en"


def roman_urdu_score(text: str) -> int:
    """How many Roman Urdu markers a text contains.

    Used to tell a Roman Urdu knowledge-base row from an English one: both use
    Latin letters, so the script alone cannot separate them.
    """
    if not text:
        return 0
    words = re.findall(r"[a-zA-Z']+", text.lower())
    return sum(1 for word in words if word in ROMAN_URDU_MARKERS)


def redact_personal_data(text: str) -> str:
    """Mask e-mail addresses and phone numbers before anything is logged."""
    if not text:
        return ""
    redacted = EMAIL_RE.sub("[email]", text)
    redacted = PHONE_RE.sub(lambda m: "[phone]" if len(re.sub(r"\D", "", m.group(0))) >= 7 else m.group(0), redacted)
    return redacted


def chunk_body(text: str) -> str:
    """The prose of a chunk, without the leading "Section:" header line.

    Chunk text is built as "section heading:\\nbody". The heading is metadata,
    not an answer, and leaking it into a reply reads like a machine dumping
    index rows.
    """
    if not text:
        return ""
    if "\n" in text:
        head, _, body = text.partition("\n")
        if head.strip().endswith(":") and len(head.strip()) < 200:
            return body.strip()
    return text.strip()


def clean_markdown(text: str) -> str:
    """Strip list markers and emphasis so a chunk can be read as an answer."""
    if not text:
        return ""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^#+\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        if line:
            lines.append(line)
    return " ".join(lines)


def first_sentences(text: str, count: int = 2, max_chars: int = 420) -> str:
    """The first `count` sentences of `text`, capped at `max_chars`."""
    cleaned = clean_markdown(text)
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?۔。])\s+", cleaned)
    picked = " ".join(s for s in sentences[:count] if s).strip()
    if not picked:
        picked = sentences[0].strip() if sentences else cleaned
    if len(picked) > max_chars:
        cut = picked[:max_chars]
        space = cut.rfind(" ")
        picked = (cut[:space] if space > max_chars * 0.6 else cut).rstrip() + "..."
    return picked
