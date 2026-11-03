from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import chromadb

from app.config import Settings
from app.embeddings import Embedder, create_embedder
from app.rag.chunker import Chunk, estimate_tokens, kb_documents, load_all_chunks

COLLECTION_NAME = "hotela_kb"


def kb_version(kb_dir: Path, chunking_signature: str = "") -> str:
    """Hash exactly what the index is built from, so a stale index is detectable.

    The knowledge files are the obvious input. The chunking settings are
    included too: changing them changes the chunks, so the old index no
    longer matches the configuration and must be rebuilt.
    """
    digest = hashlib.sha256()
    for path in sorted([*kb_documents(kb_dir), kb_dir / "plans.json"]):
        if path.exists():
            digest.update(path.relative_to(kb_dir).as_posix().encode())
            digest.update(path.read_bytes())
    if chunking_signature:
        digest.update(f"chunking:{chunking_signature}".encode())
    return digest.hexdigest()


def get_client(settings: Settings) -> chromadb.PersistentClient:
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(settings.chroma_dir))


def build_collection(settings: Settings, embedder: Embedder) -> tuple[Any, str, int, int]:
    """Rebuild the collection from the knowledge base.

    The collection is replaced, so a rebuild is idempotent: running it twice
    gives the same collection with the same version.
    """
    version = kb_version(settings.kb_dir, settings.chunking_signature)
    chunks = load_all_chunks(
        settings.kb_dir,
        version,
        max_tokens=settings.chunk_max_tokens,
        min_tokens=settings.chunk_min_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )
    client = get_client(settings)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
            "kb_version": version,
            "embedding_provider": embedder.provider,
            "embedding_model": embedder.model,
            "embedding_dimension": int(settings.embedding_dimension),
            "chunk_max_tokens": int(settings.chunk_max_tokens),
            "chunk_min_tokens": int(settings.chunk_min_tokens),
            "chunk_overlap_tokens": int(settings.chunk_overlap_tokens),
        },
    )
    for start in range(0, len(chunks), 64):
        batch = chunks[start:start + 64]
        vectors = embedder.embed([chunk.text for chunk in batch])
        for offset, vector in enumerate(vectors):
            if len(vector) != int(settings.embedding_dimension):
                raise RuntimeError(
                    f"Embedding dimension mismatch at chunk {start + offset}: "
                    f"got {len(vector)}, expected {settings.embedding_dimension}"
                )
        collection.add(
            ids=[chunk.chunk_id for chunk in batch],
            documents=[chunk.text for chunk in batch],
            embeddings=vectors,
            metadatas=[chunk.metadata for chunk in batch],
        )
    token_total = sum(estimate_tokens(chunk.text) for chunk in chunks)
    return collection, version, len(chunks), token_total


def load_collection(settings: Settings, embedder: Embedder) -> Any:
    """Load the collection, refusing one that was built with a different setup."""
    collection = get_client(settings).get_collection(COLLECTION_NAME)
    metadata = collection.metadata or {}
    if metadata.get("embedding_provider") != embedder.provider or metadata.get("embedding_model") != embedder.model:
        raise RuntimeError("Stored embedding provider/model does not match current configuration")
    stored_dimension = metadata.get("embedding_dimension")
    if stored_dimension is not None and int(stored_dimension) != int(settings.embedding_dimension):
        raise RuntimeError(
            f"The stored index uses {stored_dimension}-dimensional embeddings but the configuration "
            f"expects {settings.embedding_dimension}; rebuild the index."
        )
    return collection


def collection_info(settings: Settings) -> dict[str, Any]:
    """What the API reports about the index: version, size and dimension."""
    version = kb_version(settings.kb_dir, settings.chunking_signature)
    try:
        collection = get_client(settings).get_collection(COLLECTION_NAME)
    except Exception:
        return {
            "exists": False,
            "kb_version": version,
            "stored_kb_version": None,
            "count": 0,
            "embedding_provider": None,
            "embedding_model": None,
            "embedding_dimension": None,
        }
    metadata = collection.metadata or {}
    return {
        "exists": True,
        "kb_version": version,
        "stored_kb_version": metadata.get("kb_version"),
        "count": collection.count(),
        "embedding_provider": metadata.get("embedding_provider"),
        "embedding_model": metadata.get("embedding_model"),
        "embedding_dimension": metadata.get("embedding_dimension"),
        "chunk_max_tokens": metadata.get("chunk_max_tokens"),
        "chunk_min_tokens": metadata.get("chunk_min_tokens"),
        "chunk_overlap_tokens": metadata.get("chunk_overlap_tokens"),
    }
