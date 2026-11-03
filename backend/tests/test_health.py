"""The health checks must separate "cannot answer" from "cannot generate".

A broken vector store is fatal: the service must not start and pretend. An
unreachable model is degraded: the assistant can still answer from the
knowledge base, so it must start and say so.
"""

from __future__ import annotations

from app.config import Settings
from app.health import (
    DEGRADED,
    FATAL,
    OK,
    check_config,
    check_embeddings,
    check_provider,
    run_health_check,
)


class BrokenEmbedder:
    provider = "test"
    model = "broken"

    def embed_one(self, text):  # pragma: no cover - the error is the point
        raise RuntimeError("model files are missing")


class ShortEmbedder:
    provider = "test"
    model = "short"

    def embed_one(self, text):
        return [0.0, 0.0]


class ReadyEmbedder:
    provider = "test"
    model = "ready"

    def embed_one(self, text):
        return [0.0] * 384


class ReadyProvider:
    model = "test-model"

    def preflight(self):
        return True, "OK"


class DownProvider:
    model = "test-model"

    def preflight(self):
        return False, "the provider refused the request (401/403)"


class LooksReadyProvider:
    """A client that believes it is fine, until it is actually called."""

    model = "test-model"
    calls = 0

    def provider_status(self):
        return {"model": self.model, "state": "ready"}

    def preflight(self):
        type(self).calls += 1
        return False, "the provider refused the request (401/403)"


def test_a_missing_key_is_degraded_not_fatal():
    settings = Settings(_env_file=None, gemini_api_key="")
    report = check_config(settings)
    assert report["status"] == DEGRADED
    assert report["api_key_present"] is False
    assert "GEMINI_API_KEY" in report["detail"]


def test_a_present_key_is_ok():
    settings = Settings(_env_file=None, gemini_api_key="a-key")
    report = check_config(settings)
    assert report["status"] == OK
    assert report["api_key_present"] is True


def test_broken_embeddings_are_fatal():
    settings = Settings(_env_file=None, embedding_dimension=384)
    report = check_embeddings(settings, BrokenEmbedder())
    assert report["status"] == FATAL
    assert "model files are missing" in report["detail"]


def test_embeddings_of_the_wrong_size_are_fatal():
    settings = Settings(_env_file=None, embedding_dimension=384)
    report = check_embeddings(settings, ShortEmbedder())
    assert report["status"] == FATAL
    assert report["dimension"] == 2
    assert report["expected_dimension"] == 384


def test_embeddings_of_the_right_size_are_ok():
    settings = Settings(_env_file=None, embedding_dimension=384)
    assert check_embeddings(settings, ReadyEmbedder())["status"] == OK


def test_an_unreachable_provider_is_degraded():
    report = check_provider(DownProvider())
    assert report["status"] == DEGRADED
    assert "401/403" in report["detail"]


def test_a_reachable_provider_is_ok():
    assert check_provider(ReadyProvider())["status"] == OK


def test_a_client_without_a_probe_is_not_reported_as_broken():
    """A custom client cannot be probed; that is not evidence of a failure."""

    class Custom:
        model = "custom"

    assert check_provider(Custom())["status"] == OK


def test_no_provider_at_all_is_degraded():
    assert check_provider(None)["status"] == DEGRADED


def test_without_a_probe_a_ready_client_is_reported_as_ok():
    """The cheap check reads the client's own state and calls nothing."""
    provider = LooksReadyProvider()
    report = check_provider(provider)
    assert report["status"] == OK
    assert report["probed"] is False
    assert provider.calls == 0


def test_the_probe_calls_the_provider():
    """A key that is configured but not allowed to call the model only shows up here."""
    provider = LooksReadyProvider()
    report = check_provider(provider, probe=True)
    assert report["status"] == DEGRADED
    assert "401/403" in report["detail"]
    assert report["probed"] is True
    assert provider.calls == 1


def test_the_overall_status_is_error_when_a_component_is_fatal():
    settings = Settings(_env_file=None, gemini_api_key="")
    report = run_health_check(settings, embedder=BrokenEmbedder(), llm=DownProvider())
    assert report["status"] == "error"
    assert report["components"]["embeddings"]["status"] == FATAL


def test_the_overall_status_is_degraded_when_only_the_provider_is_down():
    settings = Settings(_env_file=None, gemini_api_key="a-key")
    report = run_health_check(settings, embedder=ReadyEmbedder(), llm=DownProvider())
    assert report["status"] == "degraded"
    assert report["components"]["provider"]["status"] == DEGRADED
    assert report["components"]["embeddings"]["status"] == OK


def test_the_report_never_carries_the_key():
    settings = Settings(_env_file=None, gemini_api_key="a-very-secret-key")
    report = run_health_check(settings, embedder=ReadyEmbedder(), llm=ReadyProvider())
    assert "a-very-secret-key" not in str(report)
