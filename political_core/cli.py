from __future__ import annotations

import argparse
import json
import os
import sys

from .cache import SQLiteCache
from .cached_providers import CachedFetcher, CachedSearchProvider
from .config import Settings
from .engine import FactCheckEngine
from .evals import evaluate_jsonl
from .fetch import SafeHttpFetcher
from .openai_reasoning import OpenAIReasoningProvider
from .output import render_persian
from .search_searxng import SearxNGSearchProvider


def _engine() -> FactCheckEngine:
    searx = os.getenv("SEARXNG_URL")
    model = os.getenv("OPENAI_MODEL")
    if not searx:
        raise RuntimeError("SEARXNG_URL is required for the CLI search provider")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for the OpenAI reasoning adapter")
    if not model:
        raise RuntimeError("OPENAI_MODEL is required; choose the model explicitly instead of relying on a stale hard-coded default")
    settings = Settings()
    cache = SQLiteCache(settings.cache_path)
    search = CachedSearchProvider(SearxNGSearchProvider(searx), cache)
    fetcher = CachedFetcher(SafeHttpFetcher(settings.fetch_timeout, settings.max_response_bytes), cache)
    return FactCheckEngine(
        search, OpenAIReasoningProvider(model), fetcher=fetcher, cache=cache,
        quick_budget=settings.quick_budget(), deep_budget=settings.deep_budget(),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="political-check")
    parser.add_argument("claim", nargs="?")
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--eval-jsonl")
    args = parser.parse_args(argv)
    if args.eval_jsonl:
        print(json.dumps(evaluate_jsonl(args.eval_jsonl), ensure_ascii=False, indent=2))
        return 0
    if not args.claim:
        parser.error("claim is required unless --eval-jsonl is used")
    try:
        result = _engine().check(args.claim, mode="deep" if args.deep else "quick", refresh=args.refresh)
    except Exception as exc:
        print(f"configuration/verification error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.as_json else render_persian(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
