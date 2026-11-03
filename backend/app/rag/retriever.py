from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.embeddings import Embedder
from app.rag.bm25 import BM25Index
from app.text import ARABIC_BLOCK

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    metadata: dict[str, Any]
    similarity: float
    score: float = 0.0
    source: str = "vector"


@dataclass
class _HybridCache:
    """BM25 index over the collection, rebuilt when the collection changes."""

    signature: tuple | None = None
    index: BM25Index | None = None
    ids: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def get(self, collection: Any) -> tuple[BM25Index, list[str]]:
        with self.lock:
            signature = self._signature(collection)
            if self.index is None or signature != self.signature:
                data = collection.get(include=["documents"])
                documents = list(data.get("documents") or [])
                ids = list(data.get("ids") or [])
                self.index = BM25Index(documents)
                self.ids = ids
                self.signature = signature
                logger.info("Built BM25 index over %d chunks", len(documents))
            return self.index, self.ids

    @staticmethod
    def _signature(collection: Any) -> tuple:
        try:
            return (collection.count(), str((collection.metadata or {}).get("kb_version", "")))
        except Exception:  # pragma: no cover - defensive
            return (-1, "")


_HYBRID_CACHE = _HybridCache()


def _chunk_script(text: str) -> str:
    if ARABIC_BLOCK.search(text or ""):
        return "arabic"
    return "latin"


def _script_boost(query: str, chunk_text: str, boost: float) -> float:
    """Reward a chunk written in the script the visitor used.

    The knowledge base carries parallel English, Urdu-script and Roman-Urdu
    rows, so the right-language row usually sits a little lower in the vector
    ranking than its English twin. A small additive bonus keeps the visitor's
    language without changing the semantic ranking.
    """
    if not boost:
        return 0.0
    query_script = _chunk_script(query)
    if query_script == "none":
        return 0.0
    chunk_script = _chunk_script(chunk_text)
    if chunk_script == query_script:
        return boost
    return -boost


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).lower()


def retrieve(
    collection: Any,
    embedder: Embedder,
    query: str,
    top_k: int = 6,
    min_similarity: float = 0.35,
    *,
    candidate_k: int | None = None,
    script_boost: float | None = None,
    hybrid: bool | None = None,
    rrf_k: int | None = None,
    dedupe: bool | None = None,
    answer_min_similarity: float | None = None,
) -> list[RetrievedChunk]:
    """Search the knowledge base and return the grounded chunks for a question.

    * `candidate_k` chunks are pulled from the vector store, filtered by
      `min_similarity`, de-duplicated, and the best `top_k` are returned.
    * `script_boost` nudges chunks written in the visitor's script.
    * `hybrid` adds a BM25 ranker fused with the vector ranker by reciprocal
      rank fusion.
    """
    candidate_k = candidate_k if candidate_k is not None else max(top_k, settings.candidate_k)
    script_boost = settings.retrieval_script_boost if script_boost is None else script_boost
    hybrid = settings.retrieval_hybrid if hybrid is None else hybrid
    rrf_k = settings.retrieval_hybrid_rrf_k if rrf_k is None else rrf_k
    dedupe = settings.retrieval_dedupe if dedupe is None else dedupe
    answer_min_similarity = (
        settings.retrieval_answer_min_similarity if answer_min_similarity is None else answer_min_similarity
    )

    query_vector = embedder.embed_one(query)
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=candidate_k,
        include=["documents", "metadatas", "distances"],
    )
    documents = result.get("documents", [[]])[0] or []
    metadatas = result.get("metadatas", [[]])[0] or []
    distances = result.get("distances", [[]])[0] or []

    scored: list[RetrievedChunk] = []
    for text, metadata, distance in zip(documents, metadatas, distances):
        dist_val = float(distance)
        if math.isnan(dist_val) or math.isinf(dist_val):
            logger.warning("Retriever encountered NaN/Inf distance: %s", distance)
            continue
        similarity = 1.0 - dist_val
        if similarity < min_similarity:
            continue
        adjusted = similarity + _script_boost(query, text or "", script_boost)
        scored.append(
            RetrievedChunk(
                text=text or "",
                metadata=metadata or {},
                similarity=similarity,
                score=adjusted,
                source="vector",
            )
        )

    if hybrid:
        scored = _fuse_with_bm25(collection, query, scored, rrf_k, script_boost)

    # The vector store returns its own ranking; the script boost can change it.
    # A stable sort keeps the original order for equal scores.
    scored.sort(key=lambda chunk: chunk.score, reverse=True)

    found: list[RetrievedChunk] = []
    seen_sections: set[str] = set()
    seen_texts: set[str] = set()
    for chunk in scored:
        identity = f"{chunk.metadata.get('file')}:{chunk.metadata.get('section')}"
        normalized = _normalize_text(chunk.text)
        if dedupe:
            if identity in seen_sections:
                continue
            if normalized and normalized in seen_texts:
                continue
        seen_sections.add(identity)
        if normalized:
            seen_texts.add(normalized)
        found.append(chunk)
        if len(found) >= top_k:
            break

    logger.debug(
        "Query: %s -> %d chunks (top_k=%d, min_sim=%.2f, candidate_k=%d, hybrid=%s)",
        query,
        len(found),
        top_k,
        min_similarity,
        candidate_k,
        hybrid,
    )
    return found


def _fuse_with_bm25(
    collection: Any,
    query: str,
    vector_chunks: list[RetrievedChunk],
    rrf_k: int,
    script_boost: float = 0.0,
) -> list[RetrievedChunk]:
    """Re-rank the vector candidates with BM25, fused by reciprocal rank.

    BM25 only re-orders chunks that already passed the vector threshold: it
    can promote a chunk that the vector store ranked low, but it can never
    introduce material the vector store considered too far away.

    The language boost is applied as a factor on the reciprocal-rank score,
    so it stays in the same units as the fusion instead of overriding it.
    """
    try:
        index, _ids = _HYBRID_CACHE.get(collection)
    except Exception as error:  # pragma: no cover - defensive
        logger.warning("BM25 index unavailable (%s); using the vector ranker only", error)
        return vector_chunks
    if index is None:
        return vector_chunks

    bm25_scores = index.scores(query)
    order = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)
    bm25_rank = {position: rank for rank, position in enumerate(order, 1)}

    position_by_text: dict[str, int] = {}
    for position, document in enumerate(index.documents):
        position_by_text.setdefault(document, position)

    fused: list[RetrievedChunk] = []
    for rank, chunk in enumerate(vector_chunks, 1):
        contribution = 1.0 / (rrf_k + rank)
        position = position_by_text.get(chunk.text)
        if position is not None and position in bm25_rank:
            contribution += 1.0 / (rrf_k + bm25_rank[position])
        factor = 1.0 + _script_boost(query, chunk.text, script_boost)
        fused.append(
            RetrievedChunk(
                text=chunk.text,
                metadata=chunk.metadata,
                similarity=chunk.similarity,
                score=contribution * factor,
                source="vector+bm25",
            )
        )
    return sorted(fused, key=lambda chunk: chunk.score, reverse=True)
