from __future__ import annotations

import os
from dataclasses import dataclass

from .models import Budget
from .primary_source import AuthorityRegistry


def _int(name:str,default:int)->int:return int(os.getenv(name,default))
def _float(name:str,default:float)->float:return float(os.getenv(name,default))


@dataclass(slots=True)
class Settings:
    cache_path:str=os.getenv("CACHE_PATH",".political-cache.sqlite3")
    cache_max_rows:int=_int("CACHE_MAX_ROWS",20_000)
    search_cache_ttl:int=_int("SEARCH_CACHE_TTL",300)
    fetch_cache_ttl:int=_int("FETCH_CACHE_TTL",600)
    fetch_timeout:float=_float("FETCH_TIMEOUT",8.0)
    max_response_bytes:int=_int("MAX_RESPONSE_BYTES",1_500_000)
    reasoning_timeout:float=_float("REASONING_TIMEOUT",30.0)
    reasoning_retries:int=max(0,min(1,_int("REASONING_RETRIES",1)))
    store_user_content:bool=os.getenv("STORE_USER_CONTENT","false").lower()=="true"

    def quick_budget(self)->Budget:
        return Budget(_int("QUICK_MAX_QUERIES",2),_int("QUICK_RESULTS_PER_QUERY",8),_int("QUICK_MAX_SOURCES",5),_int("QUICK_MAX_FETCHES",5),1,_int("QUICK_MAX_PAGE_CHARS",8000),_int("QUICK_CACHE_TTL",21600))

    def deep_budget(self)->Budget:
        return Budget(_int("DEEP_MAX_QUERIES",6),_int("DEEP_RESULTS_PER_QUERY",10),_int("DEEP_MAX_SOURCES",12),_int("DEEP_MAX_FETCHES",12),max(2,_int("DEEP_MAX_REASONING_CALLS",2)),_int("DEEP_MAX_PAGE_CHARS",14000),_int("DEEP_CACHE_TTL",3600))

    def authority_registry(self)->AuthorityRegistry:
        reg=AuthorityRegistry();raw=os.getenv("POLITICAL_AUTHORITY_DOMAINS","")
        for item in raw.split(","):
            item=item.strip()
            if not item:continue
            domain,issuer=item.split("=",1) if "=" in item else (item,item);reg.add(domain.strip(),issuer.strip())
        return reg
