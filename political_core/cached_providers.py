from __future__ import annotations
import threading
from .cache_backend import CacheBackend
from .models import SearchResult,SourceKind
from .text import fingerprint

class _RequestStats:
    def __init__(self):
        self._local=threading.local();self._lock=threading.Lock();self.total_hits=0;self.total_calls=0
    def _ensure(self):
        if not hasattr(self._local,"hits"):self._local.hits=0;self._local.calls=0
    def hit(self):
        self._ensure();self._local.hits+=1
        with self._lock:self.total_hits+=1
    def call(self):
        self._ensure();self._local.calls+=1
        with self._lock:self.total_calls+=1
    def reset(self):self._local.hits=0;self._local.calls=0
    def current(self,ttl,*,consume=True):
        self._ensure();out={"cache_hits":self._local.hits,"provider_calls":self._local.calls,"ttl_seconds":ttl}
        if consume:self.reset()
        return out
    def lifetime(self,ttl):
        with self._lock:return {"cache_hits":self.total_hits,"provider_calls":self.total_calls,"ttl_seconds":ttl}

class CachedSearchProvider:
    def __init__(self,inner,cache:CacheBackend,ttl_seconds:int=300)->None:self.inner=inner;self.cache=cache;self.ttl_seconds=max(0,int(ttl_seconds));self._stats=_RequestStats();self.bypass_cache=False
    def reset_request_stats(self)->None:self._stats.reset()
    @property
    def stats(self):return self._stats.current(self.ttl_seconds)
    @property
    def lifetime_stats(self):return self._stats.lifetime(self.ttl_seconds)
    def search(self,query:str,limit:int):
        key=f"search:v4:{limit}:{fingerprint(query)}"
        if not self.bypass_cache and self.ttl_seconds>0:
            cached=self.cache.get(key,self.ttl_seconds)
            if cached:
                self._stats.hit()
                return [SearchResult(url=x["url"],title=x["title"],snippet=x.get("snippet",""),published_at=x.get("published_at"),updated_at=x.get("updated_at"),publisher=x.get("publisher"),cited_source=x.get("cited_source"),source_kind=SourceKind(x.get("source_kind","unknown")),issuer_hint=x.get("issuer_hint"),document_type_hint=x.get("document_type_hint"),retrieval_purposes=list(x.get("retrieval_purposes",[])),retrieval_claim_ids=list(x.get("retrieval_claim_ids",[])),search_engine=x.get("search_engine")) for x in cached.get("items",[])]
        self._stats.call();items=list(self.inner.search(query,limit))
        self.cache.set(key,{"items":[{"url":x.url,"title":x.title,"snippet":x.snippet,"published_at":x.published_at,"updated_at":x.updated_at,"publisher":x.publisher,"cited_source":x.cited_source,"source_kind":x.source_kind.value,"issuer_hint":x.issuer_hint,"document_type_hint":x.document_type_hint,"retrieval_purposes":x.retrieval_purposes,"retrieval_claim_ids":x.retrieval_claim_ids,"search_engine":x.search_engine} for x in items]},self.ttl_seconds)
        return items

class CachedFetcher:
    def __init__(self,inner,cache:CacheBackend,ttl_seconds:int=600)->None:self.inner=inner;self.cache=cache;self.ttl_seconds=max(0,int(ttl_seconds));self._stats=_RequestStats();self.bypass_cache=False
    def reset_request_stats(self)->None:self._stats.reset()
    @property
    def stats(self):return self._stats.current(self.ttl_seconds)
    @property
    def lifetime_stats(self):return self._stats.lifetime(self.ttl_seconds)
    def fetch_text(self,url:str,max_chars:int,relevance_terms:str|None=None)->str:
        key=f"fetch:v4:{max_chars}:{fingerprint(url+'|'+(relevance_terms or ''))}"
        if not self.bypass_cache and self.ttl_seconds>0:
            cached=self.cache.get(key,self.ttl_seconds)
            if cached:self._stats.hit();return str(cached.get("text",""))
        self._stats.call();text=self.inner.fetch_text(url,max_chars,relevance_terms);self.cache.set(key,{"text":text},self.ttl_seconds);return text
