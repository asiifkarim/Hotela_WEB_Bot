from __future__ import annotations

import json
import logging
import re
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.datastructures import MutableHeaders

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.chat.service import ChatService
from app.config import settings
from app.db import init_db
from app.embeddings import create_embedder
from app.health import log_report, run_health_check
from app.leads.routes import router as leads_router
from app.llm.client import GeminiLLMClient
from app.logging_setup import configure_logging, new_request_id, request_id
from app.rag.index import build_collection, collection_info, load_collection

configure_logging(settings.log_level, settings.log_json)
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])
service: ChatService | None = None
health_report: dict = {}

REQUEST_ID_RE = re.compile(r"[^A-Za-z0-9._-]{1,64}")


def build_service() -> ChatService | None:
    """Build the chat service, or None when the knowledge base is unavailable.

    A named function rather than inline lifespan code so the evaluator and the
    tests can drive the real app (guards, SSE, fallback) with a stub provider.
    The LLM deadline comes from settings so LLM_TIMEOUT_SECONDS cannot be
    configured and then ignored.
    """
    embedder = create_embedder(settings.embedding_provider, settings.embedding_model, settings.gemini_api_key)
    info = collection_info(settings)
    if not info["exists"]:
        logger.warning("Chroma collection is missing; run backend/scripts/build_index.py")
    elif info["stored_kb_version"] != info["kb_version"]:
        logger.warning("KB version mismatch: stored=%s current=%s", info["stored_kb_version"], info["kb_version"])
        if settings.auto_rebuild_index:
            build_collection(settings, embedder)
    try:
        collection = load_collection(settings, embedder)
    except Exception as exc:
        logger.warning("KB collection unavailable: %s", exc)
        return None
    return ChatService(
        settings,
        collection,
        embedder,
        GeminiLLMClient(
            settings.gemini_api_key,
            settings.llm_model,
            settings.llm_timeout_seconds,
            api_version=settings.llm_api_version,
            max_retries=settings.llm_max_retries,
            retry_base_delay=settings.llm_retry_base_delay_seconds,
            retry_max_delay=settings.llm_retry_max_delay_seconds,
            temperature=settings.llm_temperature,
            max_output_tokens=settings.llm_max_output_tokens,
            safety_block_threshold=settings.llm_safety_block_threshold,
        ),
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global service, health_report
    init_db()
    service = build_service()

    if settings.health_check_on_startup:
        embedder = create_embedder(settings.embedding_provider, settings.embedding_model, settings.gemini_api_key)
        health_report = run_health_check(
            settings,
            embedder=embedder,
            collection=getattr(service, "collection", None),
            llm=getattr(service, "llm", None),
            # Booting must not spend quota or wait on a slow provider; the
            # command-line health check (npm run health) probes for real.
            provider_probe=settings.health_check_probe_provider,
        )
        log_report(health_report)
        if health_report["status"] == "error":
            message = "startup health check failed: " + ", ".join(
                name for name, component in health_report["components"].items() if component.get("status") == "fatal"
            )
            if settings.health_check_fail_fast:
                raise RuntimeError(message)
            logger.error("%s; the assistant will not be able to answer", message)
    yield


class RequestIdMiddleware:
    """Give every request an id, and put it in the logs.

    Implemented as raw ASGI so a streaming (SSE) response is not buffered.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        header = dict(scope.get("headers") or {}).get(b"x-request-id", b"").decode("latin-1")
        incoming = REQUEST_ID_RE.sub("", header)[:64]
        identifier = incoming or new_request_id()
        token = request_id.set(identifier)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = identifier
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            request_id.reset(token)
            logger.info(
                "http request",
                extra={
                    "event": "http_request",
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )


app = FastAPI(title="Hotela Public Chatbot", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(leads_router)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=settings.max_message_chars)
    history: list[dict] = Field(default_factory=list)


@app.get("/health")
def health() -> dict:
    """Component health. The report is taken at startup so the endpoint stays cheap."""
    report = dict(health_report)
    report.setdefault("status", "unknown" if service is None else "ok")
    report["kb"] = "ready" if service else "unavailable"
    report["service"] = service is not None
    return report


@app.get("/api/kb/version")
def kb_version_endpoint() -> dict:
    return collection_info(settings)


@app.post("/api/chat")
@limiter.limit(settings.rate_limit)
def chat(request: Request, payload: ChatRequest) -> StreamingResponse:
    if service is None:
        raise HTTPException(status_code=503, detail="Knowledge base is unavailable")

    def events():
        try:
            for event, value in service.stream(payload.session_id, payload.message, payload.history):
                data = json.dumps({"type": event, "value": value}, ensure_ascii=False)
                yield f"event: {event}\ndata: {data}\n\n"
        except ValueError as exc:
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'value': str(exc)})}\n\n"
        except Exception:
            logger.exception("Chat request failed")
            yield "event: error\ndata: {\"type\":\"error\",\"value\":\"The assistant is temporarily unavailable.\"}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
