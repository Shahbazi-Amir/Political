from __future__ import annotations

import argparse
import json
import os

from .cache import SQLiteCache
from .engine import FactCheckEngine
from .fetch import SafeHttpFetcher
from .openai_reasoning import OpenAIReasoningProvider
from .search_searxng import SearxNGSearchProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidence-first political fact checker")
    parser.add_argument("claim", help="claim or news statement to verify")
    parser.add_argument("--mode", choices=["quick", "deep"], default="quick")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    searx = os.environ.get("SEARXNG_URL")
    model = os.environ.get("POLITICAL_MODEL")
    if not searx:
        raise SystemExit("SEARXNG_URL is required (self-hosted SearxNG is recommended for low search cost).")
    if not model:
        raise SystemExit("POLITICAL_MODEL is required; set it to the OpenAI model you want to use.")

    engine = FactCheckEngine(
        SearxNGSearchProvider(searx),
        OpenAIReasoningProvider(model),
        fetcher=SafeHttpFetcher(),
        cache=SQLiteCache(os.environ.get("POLITICAL_CACHE", "political_cache.sqlite3")),
    )
    result = engine.check(args.claim, mode=args.mode, refresh=args.refresh)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
