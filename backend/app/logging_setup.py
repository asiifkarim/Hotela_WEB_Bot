"""Structured logging for the Hotela assistant.

Every request emits one JSON line per stage so latency, retrieval and provider
errors can be traced without reading free text. Secrets and personal data are
never written: the API key is never logged, and visitor messages are redacted
(e-mail addresses and phone numbers masked) before they reach a log record.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar

from app.text import redact_personal_data

request_id: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info",
        "thread", "threadName", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id.get(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key == "request_id":
                continue
            payload[key] = value
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        rid = getattr(record, "request_id", None) or request_id.get()
        prefix = f"[{rid}] " if rid and rid != "-" else ""
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name}: {record.getMessage()}"
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and key != "request_id"
        }
        if extras:
            base += " " + " ".join(f"{key}={value}" for key, value in extras.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return prefix + base


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    """Install the root handler. Safe to call more than once."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # These libraries are chatty at INFO and drown the request lines.
    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "google_genai", "chromadb"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_message(text: str, limit: int = 300) -> str:
    """A visitor message that is safe to write to a log: redacted and truncated."""
    return redact_personal_data(text or "")[:limit]
