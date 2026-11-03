"""Verify the generation half of the evaluator without a live provider.

The scoring code (fact correctness, faithfulness, unsupported numbers, handoff,
redirect, small talk, language) is driven end to end through the real
/api/chat SSE surface, with real retrieval over the real evaluation set. A stub
LLM is the only fake, so a provider outage cannot hide a broken metric.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "eval"))

import run_eval  # noqa: E402

from app.chat.service import ChatService  # noqa: E402
from app.config import settings  # noqa: E402
from app.embeddings import create_embedder  # noqa: E402
from app.rag.index import load_collection  # noqa: E402

# Real questions whose behaviour the pipeline fixes: three retrieve enough to
# reach the model, and three are answered before the model is ever called.
REAL_IDS = ("faq-01", "price-01", "price-02", "lang-01", "hd-01", "inj-03", "st-01")

# Answers are keyed by the exact message, and are chosen to exercise both sides of
# every metric: two fully correct, one correct but quoting a number the context
# never states, one wrong, and one correct claim the context does not support.
STUB_ANSWERS = {
    "What is Hotela?": "Hotela is a hotel and restaurant management platform by IdeoMetriX.",
    "How much is Hotela Stay?": "PKR 35,000 per branch for 6 months.",
    "What is the Hotela Dine price?": "Hotela Dine costs PKR 59,000 per month.",
    "Kya free trial milta hai?": "ji haan, har plan 7-day free trial ke saath shuru hota hai",
    "What does a restaurant invoice include?": "It records items, discount, service charge and grand total.",
    "Do you offer discounts on long contracts?": "Discounts are not confirmed; please contact hotelaapp@gmail.com.",
}


class StubLLM:
    def rewrite_query(self, message, history):
        return message

    def stream_answer(self, message, context, core_facts, history):
        yield STUB_ANSWERS.get(message, "I am not sure.")


@pytest.fixture(scope="module")
def embedder_and_collection():
    embedder = create_embedder(settings.embedding_provider, settings.embedding_model, settings.gemini_api_key)
    return embedder, load_collection(settings, embedder)


def test_generation_metrics_are_computed_correctly(monkeypatch, embedder_and_collection):
    embedder, collection = embedder_and_collection

    import app.main as main

    # The stub must be installed through the app's own factory: TestClient re-runs
    # the lifespan, which would otherwise rebuild the real Gemini client.
    monkeypatch.setattr(main, "build_service", lambda: ChatService(settings, collection, embedder, StubLLM()))

    questions, errors = run_eval.load_questions(Path(run_eval.QUESTIONS))
    assert not errors, errors
    selected = [item for item in questions if item["id"] in REAL_IDS]
    assert len(selected) == len(REAL_IDS)

    # Score retrieval exactly as the runner does, so the context the answers are
    # checked against is the context the pipeline really retrieved.
    for item in selected:
        hits, _, result = run_eval.score_retrieval(
            item["question"], run_eval.expected_sources(item), settings.top_k, collection, embedder, None
        )
        item["_hits"] = hits
        item["_retrieval"] = result

    # One question whose retrieved context is deliberately empty: the answer states
    # a real KB fact the context does not contain, so correctness must pass it while
    # faithfulness flags it. Nothing in this question comes from the pipeline.
    selected.append(
        {
            "id": "sc-01",
            "question": "What does a restaurant invoice include?",
            "kind": "easy",
            "expect": "answer",
            "answer_facts": ["service charge"],
            "sources": [],
            "language": "en",
            "_hits": [],
        }
    )

    metrics = run_eval.run_generation(selected, SimpleNamespace(question_timeout=60.0), embedder, collection)

    assert metrics["request_errors"] == 0
    assert metrics["answers_scored"] == 5, metrics
    # faq-01, price-01, lang-01 and sc-01 state every fact they are checked for;
    # price-02 answers with a price no source states.
    assert metrics["answer_correct"] == 4, metrics
    assert metrics["answer_correct_rate"] == pytest.approx(0.8)
    # price-02 checked nothing, and sc-01's claim is not in its context: neither counts.
    assert metrics["faithful"] == 3, metrics
    assert metrics["faithfulness_rate"] == pytest.approx(0.6)
    assert metrics["unsupported_number_answers"] == 1, metrics
    # hd-01 is answered by the service's handoff fallback and inj-03 by the guards,
    # so both must be correct before the model is ever reached.
    assert metrics["handoff_questions"] == 1 and metrics["handoff_correct"] == 1, metrics
    assert metrics["redirect_questions"] == 1 and metrics["redirect_correct"] == 1, metrics
    assert metrics["smalltalk_questions"] == 1 and metrics["smalltalk_correct"] == 1, metrics
    assert metrics["language_checked"] == 5 and metrics["language_correct"] == 5, metrics
