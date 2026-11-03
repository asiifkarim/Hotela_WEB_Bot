from __future__ import annotations

import logging
import queue
import re
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.chat.prompts import build_user_prompt

logger = logging.getLogger(__name__)

_DONE = object()


class LLMError(RuntimeError):
    """Base class for every provider failure the service has to reason about."""


class LLMAuthError(LLMError):
    """401/403: the key or its project cannot call the model. Retrying is pointless."""


class LLMQuotaError(LLMError):
    """429: the quota is exhausted. Retrying immediately makes it worse."""


class LLMNotFoundError(LLMError):
    """404: the model name does not exist or is not available to this project."""


class LLMTimeoutError(LLMError):
    """The model did not answer within the deadline."""


class LLMTransientError(LLMError):
    """5xx or a network fault: worth another attempt."""


class LLMClient(ABC):
    @abstractmethod
    def rewrite_query(self, message: str, history: list[dict]) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream_answer(self, message: str, context: str, core_facts: str, history: list[dict]) -> Iterator[str]:
        raise NotImplementedError


class GeminiLLMClient(LLMClient):
    """Gemini client with an explicit deadline, a typed error taxonomy and a breaker.

    Every call is bounded by `timeout_seconds`. Failures are classified so the
    service can react correctly:

    * 401/403 (auth or project access) -> no retry, the breaker opens and the
      service reports an outage instead of pretending the answer came from the
      knowledge base.
    * 429 (quota) -> no retry, the breaker opens.
    * 404 (model not found) -> no retry, the message names the model.
    * timeout -> no retry.
    * 5xx / network -> retried with exponential backoff.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 20.0,
        *,
        api_version: str = "v1beta",
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 8.0,
        temperature: float = 0.2,
        max_output_tokens: int = 400,
        safety_block_threshold: str = "BLOCK_ONLY_HIGH",
    ) -> None:
        self.model = model
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = max(1, int(max_retries))
        self.retry_base_delay = float(retry_base_delay)
        self.retry_max_delay = float(retry_max_delay)
        self.temperature = float(temperature)
        self.max_output_tokens = int(max_output_tokens)
        self.safety_block_threshold = safety_block_threshold
        self.api_version = api_version
        self.client = None
        self.last_error: str = ""
        self.last_usage: dict | None = None
        self.blocked_reason: str = ""
        if api_key and api_key != "YOUR_GEMINI_API_KEY":
            from google import genai
            from google.genai import types

            self.client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    api_version=api_version,
                    timeout=int(self.timeout_seconds * 1000),
                ),
            )
        self.quota_exhausted = False

    # ------------------------------------------------------------------ #
    # error classification
    # ------------------------------------------------------------------ #
    @staticmethod
    def _status_code(error: Exception) -> int | None:
        for attribute in ("code", "status_code", "status"):
            value = getattr(error, attribute, None)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        match = re.search(r"\b(4\d\d|5\d\d)\b", str(error))
        return int(match.group(1)) if match else None

    @classmethod
    def classify(cls, error: Exception) -> type[LLMError]:
        """Map a provider exception onto the taxonomy above."""
        if isinstance(error, LLMError):
            return type(error)
        status = cls._status_code(error)
        text = str(error).upper()
        if status in (401, 403) or "PERMISSION_DENIED" in text or "UNAUTHENTICATED" in text or "API KEY" in text:
            return LLMAuthError
        if status == 429 or "RESOURCE_EXHAUSTED" in text or "QUOTA" in text:
            return LLMQuotaError
        if status == 404 or "NOT_FOUND" in text or "is not found" in text:
            return LLMNotFoundError
        if cls._is_timeout_error(error):
            return LLMTimeoutError
        if status is not None and status >= 500:
            return LLMTransientError
        if isinstance(error, (ConnectionError, TimeoutError, OSError)):
            return LLMTransientError
        return LLMTransientError

    @staticmethod
    def _is_timeout_error(error: Exception) -> bool:
        name = type(error).__name__.lower()
        text = str(error).lower()
        return "timeout" in name or "deadline" in name or "timeout" in text or "deadline" in text or "timed out" in text

    def _timeout_error(self) -> LLMTimeoutError:
        return LLMTimeoutError(
            f"Gemini timed out after {self.timeout_seconds:g}s; using the grounded knowledge base"
        )

    # ------------------------------------------------------------------ #
    # breaker
    # ------------------------------------------------------------------ #
    @property
    def blocked(self) -> bool:
        return self.client is None or bool(self.blocked_reason)

    def provider_status(self) -> dict:
        return {
            "model": self.model,
            "api_version": self.api_version,
            "configured": self.client is not None,
            "state": "unavailable" if self.client is None else ("blocked" if self.blocked_reason else "ready"),
            "blocked_reason": self.blocked_reason or None,
            "last_error": self.last_error or None,
        }

    def _open_breaker(self, reason: str) -> None:
        self.blocked_reason = reason
        logger.error("LLM provider unavailable; circuit opened: %s", reason)

    def _unavailable_error(self) -> LLMAuthError:
        return LLMAuthError("Gemini is unavailable: set GEMINI_API_KEY in backend/.env")

    # ------------------------------------------------------------------ #
    # deadline helpers
    # ------------------------------------------------------------------ #
    def _blocking(self, call):
        """Run one blocking SDK call in a daemon thread so the deadline always wins."""
        box: dict = {}

        def worker() -> None:
            try:
                box["value"] = call()
            except BaseException as error:  # re-raised in the caller
                box["error"] = error

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(self.timeout_seconds)
        if thread.is_alive():
            raise self._timeout_error()
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def _stream_bounded(self, prompt: str) -> Iterator[str]:
        """Stream from one SDK call, abandoning it when it stalls.

        The first token must arrive within the deadline, and every later token
        must arrive within the deadline of the previous one.
        """
        chunks: "queue.Queue[object]" = queue.Queue()

        def worker() -> None:
            try:
                for response in self.client.models.generate_content_stream(
                    model=self.model, contents=prompt, config=self._generation_config()
                ):
                    usage = getattr(response, "usage_metadata", None)
                    if usage is not None:
                        self.last_usage = {
                            "prompt_tokens": getattr(usage, "prompt_token_count", None),
                            "output_tokens": getattr(usage, "candidates_token_count", None),
                            "total_tokens": getattr(usage, "total_token_count", None),
                        }
                    if response.text:
                        chunks.put(response.text)
            except BaseException as error:  # delivered in order to the caller
                chunks.put(error)
            finally:
                chunks.put(_DONE)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            try:
                item = chunks.get(timeout=self.timeout_seconds)
            except queue.Empty:
                raise self._timeout_error() from None
            if item is _DONE:
                return
            if isinstance(item, BaseException):
                raise item
            yield str(item)

    # ------------------------------------------------------------------ #
    # generation configuration
    # ------------------------------------------------------------------ #
    def _generation_config(self):
        from google.genai import types

        config: dict = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        threshold = getattr(types.HarmBlockThreshold, self.safety_block_threshold, None)
        if threshold is not None:
            config["safety_settings"] = [
                types.SafetySetting(category=category, threshold=threshold)
                for category in (
                    types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                )
            ]
        return types.GenerateContentConfig(**config)

    # ------------------------------------------------------------------ #
    # calls
    # ------------------------------------------------------------------ #
    def _generate(self, prompt: str) -> str:
        if self.client is None:
            raise self._unavailable_error()
        if self.blocked_reason:
            raise LLMError(self.blocked_reason)
        if self.quota_exhausted:
            raise LLMQuotaError("Gemini quota is exhausted; using the grounded knowledge base")

        last: Exception | None = None
        for attempt in range(self.max_retries):
            if attempt:
                delay = min(self.retry_base_delay * (2 ** (attempt - 1)), self.retry_max_delay)
                logger.warning(
                    "Retrying Gemini call in %.1fs (attempt %d/%d)", delay, attempt + 1, self.max_retries
                )
                time.sleep(delay)
            try:
                response = self._blocking(
                    lambda: self.client.models.generate_content(
                        model=self.model, contents=prompt, config=self._generation_config()
                    )
                )
                return getattr(response, "text", "") or ""
            except Exception as error:
                last = error
                kind = self.classify(error)
                self.last_error = f"{kind.__name__}: {error}"
                if kind is LLMTimeoutError:
                    raise self._timeout_error() from error
                if kind is LLMAuthError:
                    self._open_breaker(
                        "Gemini refused the request (401/403). The API key or its Google Cloud project "
                        "is not allowed to call this model. Check the Generative Language API for the "
                        "project and the key, then restart the service."
                    )
                    raise LLMAuthError(self.blocked_reason) from error
                if kind is LLMQuotaError:
                    self.quota_exhausted = True
                    self._open_breaker("Gemini quota is exhausted; using the grounded knowledge base")
                    raise LLMQuotaError(self.blocked_reason) from error
                if kind is LLMNotFoundError:
                    message = (
                        f"Gemini model '{self.model}' was not found or is not available to this project. "
                        "Set LLM_MODEL to a model the key can call."
                    )
                    self._open_breaker(message)
                    raise LLMNotFoundError(message) from error
                # transient: try again
        # The provider's own exception is raised, so the caller sees the real
        # failure; the classification is kept in self.last_error.
        if last is not None:
            raise last
        raise LLMTransientError(f"Gemini failed after {self.max_retries} attempts")

    def preflight(self) -> tuple[bool, str]:
        """One bounded probe, so a caller can tell a provider outage from bad answers."""
        try:
            text = self._generate("Reply with the single word OK.")
        except Exception as error:
            return False, f"{type(error).__name__}: {error}"
        if text.strip():
            return True, text.strip()[:40]
        return False, "provider returned an empty answer"

    def rewrite_query(self, message: str, history: list[dict]) -> str:
        prompt = (
            "Rewrite this Hotela visitor question as one standalone English search query. "
            "Return only the query, no punctuation, no explanation.\n"
            f"Question: {message}"
        )
        return self._generate(prompt) or message

    def stream_answer(self, message: str, context: str, core_facts: str, history: list[dict]) -> Iterator[str]:
        if self.client is None:
            raise self._unavailable_error()
        if self.blocked_reason:
            raise LLMError(self.blocked_reason)
        if self.quota_exhausted:
            raise LLMQuotaError("Gemini quota is exhausted; using the grounded knowledge base")
        prompt = build_user_prompt(core_facts=core_facts, context=context, question=message, history=history)
        logger.debug("final prompt", extra={"event": "llm_prompt", "prompt": prompt})
        produced = False
        last: Exception | None = None
        for attempt in range(self.max_retries):
            if attempt:
                delay = min(self.retry_base_delay * (2 ** (attempt - 1)), self.retry_max_delay)
                logger.warning(
                    "Retrying Gemini stream in %.1fs (attempt %d/%d)", delay, attempt + 1, self.max_retries
                )
                time.sleep(delay)
            produced = False
            try:
                for chunk in self._stream_bounded(prompt):
                    produced = True
                    yield chunk
                return
            except Exception as error:
                last = error
                kind = self.classify(error)
                self.last_error = f"{kind.__name__}: {error}"
                if kind is LLMTimeoutError:
                    raise self._timeout_error() from error
                if kind is LLMAuthError:
                    self._open_breaker(
                        "Gemini refused the request (401/403). The API key or its Google Cloud project "
                        "is not allowed to call this model. Check the Generative Language API for the "
                        "project and the key, then restart the service."
                    )
                    raise LLMAuthError(self.blocked_reason) from error
                if kind is LLMQuotaError:
                    self.quota_exhausted = True
                    self._open_breaker("Gemini quota is exhausted; using the grounded knowledge base")
                    raise LLMQuotaError(self.blocked_reason) from error
                if kind is LLMNotFoundError:
                    message = (
                        f"Gemini model '{self.model}' was not found or is not available to this project. "
                        "Set LLM_MODEL to a model the key can call."
                    )
                    self._open_breaker(message)
                    raise LLMNotFoundError(message) from error
                # A partial answer already reached the visitor; never restart it.
                if produced:
                    raise
        if last is not None:
            raise last
        raise LLMTransientError(f"Gemini failed after {self.max_retries} attempts")
