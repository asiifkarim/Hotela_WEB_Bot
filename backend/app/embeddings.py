from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable


class Embedder(ABC):
    provider: str
    model: str

    @abstractmethod
    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class GeminiEmbedder(Embedder):
    provider = "gemini"

    def __init__(self, model: str, api_key: str = "") -> None:
        self.model = model
        self.api_key = api_key
        if not api_key or api_key == "YOUR_GEMINI_API_KEY":
            raise RuntimeError("GEMINI_API_KEY is not configured")
        from google import genai
        self._client = genai.Client(api_key=api_key)

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        values = list(texts)
        response = self._client.models.embed_content(model=self.model, contents=values)
        embeddings = [item.values for item in response.embeddings]
        return self._validate(embeddings)

    @staticmethod
    def _validate(embeddings: list[list[float]]) -> list[list[float]]:
        import math
        for i, vec in enumerate(embeddings):
            if not vec or any(math.isnan(x) or math.isinf(x) for x in vec):
                raise RuntimeError(f"Embedding computation produced invalid (NaN or Inf) values at index {i}")
        return embeddings


class HuggingFaceEmbedder(Embedder):
    provider = "huggingface"

    def __init__(self, model: str) -> None:
        self.model = model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("EMBEDDING_PROVIDER=local requires sentence-transformers") from exc
        self._model = SentenceTransformer(model)

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        encoded = self._model.encode(list(texts), normalize_embeddings=True).tolist()
        return self._validate(encoded)

    def embed_query(self, text: str) -> list[float]:
        encoded = self._model.encode([text], normalize_embeddings=True)[0].tolist()
        return self._validate([encoded])[0]

    def embed_one(self, text: str) -> list[float]:
        return self.embed_query(text)

    @staticmethod
    def _validate(embeddings: list[list[float]]) -> list[list[float]]:
        import math
        for i, vec in enumerate(embeddings):
            if not vec or any(math.isnan(x) or math.isinf(x) for x in vec):
                raise RuntimeError(f"Embedding computation produced invalid (NaN or Inf) values at index {i}")
        return embeddings


def create_embedder(provider: str, model: str, api_key: str = "") -> Embedder:
    if provider == "gemini":
        return GeminiEmbedder(model, api_key)
    if provider in {"huggingface", "local"}:
        return HuggingFaceEmbedder(model)
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")

