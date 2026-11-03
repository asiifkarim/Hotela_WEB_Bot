"""The model call must fail fast into the documented fallback, not hang.

The Google SDK is not called here: a stand-in client makes the timing behaviour
deterministic, so these tests are fast and provider-independent.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from app.chat.service import ChatService
from app.config import ROOT_DIR
from app.llm.client import GeminiLLMClient

TIMEOUT = 0.3


class FakeModels:
    def __init__(self, *, delay: float = 0.0, error: Exception | None = None, text: str = "ok", chunks: tuple[str, ...] | None = None):
        self.delay = delay
        self.error = error
        self.text = text
        self.chunks = chunks
        self.calls = 0

    def generate_content(self, model: str, contents: str, config=None):
        self.calls += 1
        time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(text=self.text)

    def generate_content_stream(self, model: str, contents: str, config=None):
        self.calls += 1
        if self.chunks is None:
            time.sleep(self.delay)
            if self.error is not None:
                raise self.error
            yield SimpleNamespace(text=self.text)
            return
        for chunk in self.chunks:
            time.sleep(self.delay)
            if self.error is not None:
                raise self.error
            yield SimpleNamespace(text=chunk)


class FakeClient:
    def __init__(self, models: FakeModels):
        self.models = models


def make_client(models: FakeModels, timeout: float = TIMEOUT) -> GeminiLLMClient:
    client = GeminiLLMClient("test-key", "test-model", timeout)
    client.client = FakeClient(models)  # type: ignore[assignment]
    return client


def test_blocking_call_times_out_once_and_does_not_retry():
    models = FakeModels(delay=3.0)
    client = make_client(models)  # built before the timer: SDK setup is not part of the deadline
    started = time.perf_counter()
    try:
        client.rewrite_query("how much is Hotela Stay?", [])
    except RuntimeError as error:
        assert "timed out after" in str(error)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("a hanging provider must raise so the service can fall back")
    elapsed = time.perf_counter() - started
    assert elapsed < 1.5, f"took {elapsed:.1f}s; the deadline did not win"
    assert models.calls == 1, f"a timeout must not be retried, calls={models.calls}"


def test_stream_fails_fast_when_the_first_token_is_late():
    models = FakeModels(delay=3.0)
    client = make_client(models)
    started = time.perf_counter()
    try:
        list(client.stream_answer("hi", "context", "facts", []))
    except RuntimeError as error:
        assert "timed out after" in str(error)
    else:  # pragma: no cover
        raise AssertionError("a stalled stream must raise")
    assert time.perf_counter() - started < 1.5
    assert models.calls == 1


def test_stream_delivers_chunks_in_order():
    client = make_client(FakeModels(chunks=("Hel", "lo", " there")))
    assert "".join(client.stream_answer("hi", "context", "facts", [])) == "Hello there"


def test_other_errors_are_retried_but_timeouts_are_not():
    retried = FakeModels(error=ValueError("boom"))
    with_retries = make_client(retried)
    try:
        with_retries.rewrite_query("q", [])
    except ValueError:
        pass
    assert retried.calls == 3, "a transient error should still be retried three times"

    timed_out = FakeModels(error=TimeoutError("deadline exceeded"))
    fast = make_client(timed_out)
    try:
        fast.rewrite_query("q", [])
    except RuntimeError as error:
        assert "timed out after" in str(error)
    assert timed_out.calls == 1, "an SDK-reported timeout must not be retried"


def test_quota_error_short_circuits_and_is_not_retried():
    error = ValueError("429 RESOURCE_EXHAUSTED")
    models = FakeModels(error=error)
    client = make_client(models)
    for _ in range(2):
        try:
            client.rewrite_query("q", [])
        except RuntimeError as runtime_error:
            assert "quota is exhausted" in str(runtime_error)
    assert models.calls == 1, "an exhausted quota must stop calling the provider"


def test_preflight_reports_an_unavailable_provider():
    slow = make_client(FakeModels(delay=3.0))
    started = time.perf_counter()
    ready, reason = slow.preflight()
    assert ready is False
    assert "timed out after" in reason
    assert time.perf_counter() - started < 1.5, "preflight must be bounded by the same deadline"

    healthy = make_client(FakeModels(text="OK"))
    ready, reason = healthy.preflight()
    assert ready is True and reason == "OK"


class DummySettings:
    query_rewrite = False
    top_k = 6
    min_similarity = 0.35
    kb_dir = ROOT_DIR / "kb"


class FailingLLM:
    def rewrite_query(self, message, history):
        return message

    def stream_answer(self, message, context, core_facts, history):
        raise RuntimeError("Gemini did not answer within 20s; using the grounded knowledge base")


class DummyEmbedder:
    def embed_one(self, text):
        return [0.0]


class ContactCollection:
    def query(self, **kwargs):
        return {
            "documents": [["Support and contact:\nEmail: hotelaapp@gmail.com"]],
            "metadatas": [[{"file": "app_how_to.md", "section": "Support and contact"}]],
            "distances": [[0.2]],
        }


def test_service_falls_back_to_grounded_answer_when_the_provider_fails():
    service = ChatService(DummySettings(), ContactCollection(), DummyEmbedder(), FailingLLM())
    events = list(service.stream("fallback", "How can I contact Hotela support?", []))
    answer = "".join(value for event, value in events if event == "token")
    assert "hotelaapp@gmail.com" in answer
    assert events[-1] == ("done", "")
