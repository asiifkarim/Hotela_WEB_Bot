"""Build or verify the Hotela knowledge base index.

    python backend/scripts/build_index.py            # rebuild the index
    python backend/scripts/build_index.py --check    # verify only, exit 1 if stale

The rebuild is idempotent: the collection is replaced, so running it twice
gives the same collection with the same version. The verification compares the
index on disk with the knowledge base and the current configuration, so a
stale index is reported instead of silently serving old answers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings
from app.embeddings import create_embedder
from app.rag.chunker import kb_documents, token_estimator
from app.rag.index import build_collection, collection_info, load_collection


def verify(embedder) -> tuple[bool, list[str]]:
    """Compare the stored index with the knowledge base and the configuration."""
    problems: list[str] = []
    info = collection_info(settings)
    if not info["exists"]:
        return False, ["the Chroma collection is missing"]
    if info["stored_kb_version"] != info["kb_version"]:
        problems.append(
            f"the index was built from another knowledge base version "
            f"(stored {info['stored_kb_version']}, current {info['kb_version']})"
        )
    if info["embedding_provider"] != embedder.provider or info["embedding_model"] != embedder.model:
        problems.append(
            f"the index uses {info['embedding_provider']}:{info['embedding_model']} "
            f"but the configuration asks for {embedder.provider}:{embedder.model}"
        )
    stored_dimension = info.get("embedding_dimension")
    if stored_dimension is not None and int(stored_dimension) != int(settings.embedding_dimension):
        problems.append(
            f"the index stores {stored_dimension}-dimensional embeddings, "
            f"the configuration expects {settings.embedding_dimension}"
        )
    try:
        collection = load_collection(settings, embedder)
        count = collection.count()
    except Exception as error:
        problems.append(f"the collection cannot be opened: {error}")
        count = 0
    return not problems, problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the index without rebuilding it")
    args = parser.parse_args()

    embedder = create_embedder(settings.embedding_provider, settings.embedding_model, settings.gemini_api_key)

    if args.check:
        healthy, problems = verify(embedder)
        info = collection_info(settings)
        print(f"Index exists: {info['exists']}")
        print(f"Chunks: {info.get('count')}")
        print(f"kb_version: {info.get('kb_version')}")
        print(f"Stored kb_version: {info.get('stored_kb_version')}")
        print(f"Embeddings: {info.get('embedding_provider')}:{info.get('embedding_model')} ({info.get('embedding_dimension')}d)")
        if healthy:
            print("OK: the index matches the knowledge base and the configuration.")
            raise SystemExit(0)
        print("STALE INDEX:")
        for problem in problems:
            print(f"  - {problem}")
        print("Run: python backend/scripts/build_index.py")
        raise SystemExit(1)

    _collection, version, count, tokens = build_collection(settings, embedder)
    documents = len(kb_documents(settings.kb_dir)) + int((settings.kb_dir / "plans.json").exists())
    print(f"Documents loaded: {documents}")
    print(f"Token estimator: {token_estimator()}")
    print(f"Built collection: {count} chunks")
    print(f"Embeddings generated: {count}")
    print(f"kb_version: {version}")
    print(f"Token total: {tokens}")
    healthy, problems = verify(embedder)
    if not healthy:
        print("WARNING: the freshly built index did not verify:")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)
    print("Verified: the index matches the knowledge base and the configuration.")
