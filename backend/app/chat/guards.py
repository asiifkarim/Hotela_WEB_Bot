"""Input guards: size limits, injection detection and history sanitising.

The guards run before anything else in the pipeline. They cap the work a
single request can cause, strip control characters, and flag attempts to talk
the model out of its instructions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Attempts to redirect the assistant away from its instructions.
# Kept specific on purpose: a false positive sends a legitimate question to
# the redirect answer, so only unambiguous phrasings are listed.
INJECTION_PATTERNS = (
    r"ignore\s+(?:\w+\s+){0,3}instructions?",
    r"disregard (all|any|previous|the|your|any of) (instructions?|rules?|prompts?|guardrails?)",
    r"forget (all|any|your|everything|all previous)",
    r"reveal (the |your )?(system|developer|hidden) (prompt|instructions?|rules?)",
    r"(show|print|repeat|output|leak|dump|display)\s+(me\s+)?(your|the)\s+(system|developer|hidden|initial)?\s*prompt",
    r"show me your prompt",
    r"what (are|is) your (system |developer )?(prompt|instructions?)",
    r"repeat (the |everything |all )?(words|text|content) (above|before)",
    r"pretend (you are|to be)",
    r"act as (a|an|if) ",
    r"you are now",
    r"new instructions?\s*[:\-]",
    r"jailbreak|do anything now|developer mode|dan mode",
    r"bypass (your|the|all) (rules?|safety|guardrails?|filters?|restrictions?)",
    r"without (any )?(restrictions?|filters?|rules?)",
)

OFF_TOPIC_HINTS = ("weather", "sports score", "recipe", "stock price", "politics", "movie review")

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

DEFAULT_MAX_MESSAGE_CHARS = 500
DEFAULT_MAX_TURNS = 10
DEFAULT_MAX_TURN_CHARS = 2000


@dataclass(frozen=True)
class GuardResult:
    message: str
    history: list[dict]
    injection: bool
    off_topic: bool


def _clean_turn(turn: dict, max_chars: int) -> dict | None:
    """One history turn, sanitised. Anything that is not user/assistant text is dropped."""
    if not isinstance(turn, dict):
        return None
    role = str(turn.get("role", "")).lower()
    if role not in ("user", "assistant"):
        return None
    content = CONTROL_CHARS.sub("", str(turn.get("content", ""))).strip()
    if not content:
        return None
    return {"role": role, "content": content[:max_chars]}


def apply_guards(
    message: str,
    history: list[dict] | None = None,
    *,
    max_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
    max_turns: int = DEFAULT_MAX_TURNS,
    max_turn_chars: int = DEFAULT_MAX_TURN_CHARS,
) -> GuardResult:
    """Clean the visitor message and the conversation history.

    Raises ValueError when the message is longer than the configured limit; the
    API turns that into a 422 instead of spending a model call on it.
    """
    clean = CONTROL_CHARS.sub("", message or "").strip()
    if len(clean) > max_chars:
        raise ValueError(f"Message must be {max_chars} characters or fewer")
    lower = clean.lower()
    injection = any(re.search(pattern, lower) for pattern in INJECTION_PATTERNS)
    off_topic = any(hint in lower for hint in OFF_TOPIC_HINTS)
    safe_history = [
        cleaned
        for cleaned in (_clean_turn(turn, max_turn_chars) for turn in (history or [])[-max_turns:])
        if cleaned is not None
    ]
    return GuardResult(clean, safe_history, injection, off_topic)
