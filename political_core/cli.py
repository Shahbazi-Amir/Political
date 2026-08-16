from __future__ import annotations
import argparse,json,os,sys
from .cache_backend import build_cache_backend
from .cached_providers import CachedFetcher,CachedSearchProvider
from .config import Settings
from .engine import FactCheckEngine
from .evals import evaluate_jsonl
from .fetch import SafeHttpFetcher
from .openai_reasoning import OpenAIReasoningProvider
from .output import render_persian
from .search_searxng import SearxNGSearchProvider
from .source_policy import SourcePolicy

def _engine()->FactCheckEngine:
    searx=os.getenv("SEARXNG_URL");model=os.getenv("OPENAI_MODEL")
    if not searx:raise RuntimeError("SEARXNG_URL is required for the CLI search provider")
    if not os.getenv("OPENAI_API_KEY"):raise RuntimeError("OPENAI_API_KEY is required for the OpenAI reasoning adapter")
    if not model:raise RuntimeError("OPENAI_MODEL is required; select it explicitly")
    settings=Settings();cache=build_cache_backend(settings.cache_backend,sqlite_path=settings.cache_path,max_rows=settings.cache_max_rows,redis_url=settings.redis_url)
    search=CachedSearchProvider(SearxNGSearchProvider(searx,settings.fetch_timeout,settings.max_response_bytes),cache,settings.search_cache_ttl);fetcher=CachedFetcher(SafeHttpFetcher(settings.fetch_timeout,settings.max_response_bytes),cache,settings.fetch_cache_ttl);policy=SourcePolicy(authority_registry=settings.authority_registry());reasoner=OpenAIReasoningProvider(model,max_output_tokens=int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS","1200")),timeout=settings.reasoning_timeout,max_retries=settings.reasoning_retries)
    return FactCheckEngine(search,reasoner,fetcher=fetcher,cache=cache,source_policy=policy,quick_budget=settings.quick_budget(),deep_budget=settings.deep_budget())
def main(argv=None)->int:
    parser=argparse.ArgumentParser(prog="political-check");parser.add_argument("claim",nargs="?");parser.add_argument("--deep",action="store_true");parser.add_argument("--json",action="store_true",dest="as_json");parser.add_argument("--refresh",action="store_true");parser.add_argument("--eval-jsonl");args=parser.parse_args(argv)
    if args.eval_jsonl:print(json.dumps(evaluate_jsonl(args.eval_jsonl),ensure_ascii=False,indent=2));return 0
    if not args.claim:parser.error("claim is required unless --eval-jsonl is used")
    try:result=_engine().check(args.claim,mode="deep" if args.deep else "quick",refresh=args.refresh)
    except Exception as exc:print(f"configuration/verification error: {exc}",file=sys.stderr);return 2
    print(json.dumps(result.to_dict(),ensure_ascii=False,indent=2) if args.as_json else render_persian(result));return 0
if __name__=="__main__":raise SystemExit(main())
