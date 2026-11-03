"""Check that the Hotela assistant can actually answer.

    python backend/scripts/health_check.py                # report and exit 0 unless fatal
    python backend/scripts/health_check.py --require-provider   # also fail if the model is down
    python backend/scripts/health_check.py --no-probe     # do not call the provider
    python backend/scripts/health_check.py --json         # machine readable output

By default the provider is probed with one short call, because "a key is
configured" and "the key may call the model" are different things: a valid key
on a project that is not allowed to call the model only shows up in a real
call. `--no-probe` skips it (no quota, no waiting).

Exit codes:
    0  healthy, or degraded (the assistant can still answer from the knowledge base)
    1  fatal: the assistant cannot answer (no index, stale index, broken embeddings)
    2  the provider is required but unavailable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.config import settings
from app.embeddings import create_embedder
from app.health import run_health_check
from app.llm.client import GeminiLLMClient
from app.rag.index import collection_info, load_collection


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--require-provider", action="store_true", help="fail when the model cannot be called")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="do not call the provider; report only what the client knows about itself",
    )
    args = parser.parse_args()

    embedder = create_embedder(settings.embedding_provider, settings.embedding_model, settings.gemini_api_key)
    collection = None
    try:
        collection = load_collection(settings, embedder)
    except Exception as error:
        print(f"knowledge base unavailable: {error}", file=sys.stderr)

    llm = GeminiLLMClient(
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
    )

    report = run_health_check(
        settings,
        embedder=embedder,
        collection=collection,
        llm=llm,
        probe_provider=True,
        provider_probe=not args.no_probe,
    )
    report["index"] = collection_info(settings)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"status: {report['status']}")
        print(f"checked at: {report['checked_at']}")
        for name, component in report["components"].items():
            detail = component.get("detail")
            print(f"  {name:<13} {component.get('status'):<9}{' - ' + detail if detail else ''}")

    if report["status"] == "error":
        return 1
    if args.require_provider and report["components"].get("provider", {}).get("status") != "ok":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
