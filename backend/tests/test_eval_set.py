"""The evaluation set must stay honest: real sources, real checks, no English-only traps."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "eval"))

import run_eval  # noqa: E402  (the runner is the single source for the set's rules)

from app.config import settings  # noqa: E402

LANGUAGE_NEUTRAL = ("hotela",)


def load() -> list[dict]:
    questions, errors = run_eval.load_questions(Path(run_eval.QUESTIONS))
    assert not errors, errors
    return questions


def test_eval_set_is_valid_and_every_source_section_exists():
    questions = load()
    assert 40 <= len(questions) <= 60, len(questions)
    assert not run_eval.check_sources(questions)
    ids = [question["id"] for question in questions]
    assert len(set(ids)) == len(ids)


def test_eval_set_covers_the_canonical_topics_and_kinds():
    questions = load()
    covered = {source["file"] for question in questions for source in question.get("sources") or []}
    for topic in ("app_how_to.md", "bookings.md", "customers.md", "faq.md", "finances.md", "invoices.md", "policies.md", "rooms_pricing.md", "plans.json"):
        assert topic in covered, f"{topic} is not covered by any question"
    kinds = {question["kind"] for question in questions}
    assert kinds == {"easy", "multi-step", "handoff", "language", "injection", "smalltalk"}
    assert sum(1 for question in questions if question["kind"] == "handoff") >= 8
    assert sum(1 for question in questions if question["kind"] == "multi-step") >= 5


def test_language_questions_cannot_require_english_only_words():
    """Guards the GAPS item: an Urdu answer cannot contain English-only facts."""
    questions = load()
    language_questions = [question for question in questions if question.get("language") in {"ru", "ur"}]
    assert len(language_questions) >= 4
    for question in language_questions:
        for fact in question.get("answer_facts") or []:
            if isinstance(fact, list):
                continue
            neutral = any(fact.lower().startswith(prefix) for prefix in LANGUAGE_NEUTRAL) or any(character.isdigit() for character in fact)
            assert neutral, (
                f"{question['id']}: the fact '{fact}' is English-only; use alternatives "
                "[['urdu', 'english']] or a language-neutral token such as a number or a product name"
            )


def test_handoff_and_redirect_questions_never_assert_facts():
    questions = load()
    with_sources = 0
    for question in questions:
        if question["expect"] in {"handoff", "redirect", "smalltalk"}:
            assert not question.get("answer_facts"), question["id"]
        if question["expect"] == "handoff":
            # Most handoff questions should name the section that documents the
            # gap, so the run can check we retrieve it instead of guessing. A
            # question nothing in the KB covers (discounts) has no such section.
            with_sources += int(bool(question.get("sources")))
    assert with_sources >= 8, with_sources


def test_baseline_matches_the_current_retrieval_configuration():
    baseline_path = Path(run_eval.BASELINE)
    if not baseline_path.exists():
        pytest.skip("no baseline recorded yet")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert baseline["top_k"] == settings.top_k
    assert baseline["embedding_provider"] == settings.embedding_provider
    assert baseline["embedding_model"] == settings.embedding_model
    for key in ("hit_1", "hit_k", "mrr"):
        assert isinstance(baseline["retrieval"][key], float)
