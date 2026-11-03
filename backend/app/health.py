"""Startup and on-demand health checks.

The checks exist so a broken deployment says so, loudly, instead of quietly
answering visitors with "I don't know". They are grouped in two:

* **fatal** - the assistant cannot answer at all (no vector store, a stale
  index, broken embeddings). The service should refuse to start.
* **degraded** - the assistant can still answer from the knowledge base, but
  the model is unreachable (an invalid key, a blocked project, no quota).
  The service starts and says so in the logs and in /health.

No check ever prints the API key; only where it came from.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

FATAL = "fatal"
DEGRADED = "degraded"
OK = "ok"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_config(settings: Settings) -> dict[str, Any]:
    """Is the service configured well enough to talk to a provider?"""
    key_present = bool(settings.has_api_key)
    return {
        "status": OK if key_present else DEGRADED,
        "api_key_present": key_present,
        "api_key_source": settings.api_key_source,
        "llm_model": settings.llm_model,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "detail": None if key_present else "GEMINI_API_KEY is not set; the assistant will answer from the knowledge base only",
    }


def check_embeddings(settings: Settings, embedder) -> dict[str, Any]:
    """Can we embed, and is the vector size what the index expects?"""
    try:
        vector = embedder.embed_one("Hotela health check")
    except Exception as error:
        return {
            "status": FATAL,
            "provider": getattr(embedder, "provider", "unknown"),
            "model": getattr(embedder, "model", "unknown"),
            "detail": f"{type(error).__name__}: {error}",
        }
    dimension = len(vector)
    expected = int(settings.embedding_dimension)
    status = OK if dimension == expected else FATAL
    return {
        "status": status,
        "provider": getattr(embedder, "provider", "unknown"),
        "model": getattr(embedder, "model", "unknown"),
        "dimension": dimension,
        "expected_dimension": expected,
        "detail": None if status == OK else f"embedding size {dimension} does not match EMBEDDING_DIMENSION={expected}",
    }


def check_vector_store(settings: Settings, collection) -> dict[str, Any]:
    """Does the index exist, and does it match the knowledge base on disk?"""
    from app.rag.index import collection_info

    info = collection_info(settings)
    if not info.get("exists"):
        return {
            "status": FATAL,
            "detail": "the Chroma collection is missing; run backend/scripts/build_index.py",
        }
    stored = info.get("stored_kb_version")
    current = info.get("kb_version")
    status = OK if stored == current else FATAL
    dimension = None
    try:
        sample = collection.get(limit=1, include=["embeddings"])
        embeddings = (sample or {}).get("embeddings") or []
        if len(embeddings) and embeddings[0] is not None:
            dimension = len(embeddings[0])
    except Exception:
        dimension = None
    return {
        "status": status,
        "count": info.get("count"),
        "kb_version": current,
        "stored_kb_version": stored,
        "dimension": dimension,
        "detail": None if status == OK else "the stored index is from a different knowledge base version; rebuild it",
    }


def check_provider(llm, *, probe: bool = False) -> dict[str, Any]:
    """Can the model be called at all?

    With `probe=False` (the default) the check only looks at what the client
    already knows: is a key configured, is the circuit breaker closed. That
    costs nothing, but it cannot see a key that is valid and a project that is
    not allowed to call the model.

    With `probe=True` the check makes one bounded call to the provider. That is
    the only way to tell "configured" from "usable", so it is what the
    command-line health check does.
    """
    if llm is None:
        return {"status": DEGRADED, "detail": "no model client configured", "probed": False}
    status = getattr(llm, "provider_status", None)
    if callable(status):
        report = status()
    else:
        report = {"model": getattr(llm, "model", "unknown")}
    if not probe and report.get("state") == "ready":
        report["status"] = OK
        report["detail"] = None
        report["probed"] = False
        return report
    if not hasattr(llm, "preflight"):
        # A client without a probe (a test double, or a custom provider) cannot
        # be checked; do not report a failure it may not have.
        report["status"] = OK
        report["detail"] = None
        report["probed"] = False
        return report
    ready, reason = llm.preflight()
    report["status"] = OK if ready else DEGRADED
    report["detail"] = None if ready else reason
    report["probed"] = True
    return report


def run_health_check(
    settings: Settings,
    embedder=None,
    collection=None,
    llm=None,
    *,
    probe_provider: bool = True,
    provider_probe: bool = False,
) -> dict[str, Any]:
    """Run every check and return one report.

    `probe_provider` decides whether the provider is checked at all;
    `provider_probe` decides whether that check calls the provider. The
    startup path only reads the client's state (no quota, no latency); the
    command-line health check makes the call, because that is the only way to
    find out whether the key and the project may use the model.
    """
    components: dict[str, Any] = {"config": check_config(settings)}

    if embedder is not None:
        components["embeddings"] = check_embeddings(settings, embedder)
    if collection is not None:
        components["vector_store"] = check_vector_store(settings, collection)
    if probe_provider and llm is not None:
        components["provider"] = check_provider(llm, probe=provider_probe)

    states = [component.get("status", OK) for component in components.values()]
    if FATAL in states:
        overall = "error"
    elif DEGRADED in states:
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "checked_at": _now(),
        "components": components,
        "kb_chunks": components.get("vector_store", {}).get("count"),
        "kb_version": components.get("vector_store", {}).get("kb_version"),
    }


def log_report(report: dict[str, Any]) -> None:
    """Print the report in a way that is useful in a terminal and in a log."""
    status = report.get("status")
    level = logging.ERROR if status == "error" else logging.WARNING if status == "degraded" else logging.INFO
    logger.log(level, "health check: %s", status, extra={"health": report})
    for name, component in report.get("components", {}).items():
        detail = component.get("detail")
        logger.log(
            level if component.get("status") == "fatal" else logging.INFO,
            "health %s: %s%s",
            name,
            component.get("status"),
            f" - {detail}" if detail else "",
        )
