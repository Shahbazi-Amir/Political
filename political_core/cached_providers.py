from __future__ import annotations
from .cache_backend import CacheBackend
from .models import SearchResult,SourceKind
from .text import fingerprint
class CachedSearchProvider:
    def __init__(self,inner,cache:CacheBackend,ttl_seconds:int=300)->None:self.inner=inner;self.cache=cache;self.ttl_seconds=max(0,int(ttl_seconds));self.hits=0;self.calls=0;self.bypass_cache=False
    @property
    def stats(self):return {"cache_hits":self.hits,"provider_calls":self.calls,"ttl_seconds":self.ttl_seconds}
    def search(self,query:str,limit:int):
        key=f"search:v3:{limit}:{fingerprint(query)}"
        if not self.bypass_cache and self.ttl_seconds>0:
            cached=self.cache.get(key,self.ttl_seconds)
            if cached:
                self.hits+=1
                return [SearchResult(url=x["url"],title=x["title"],snippet=x.get("snippet",""),published_at=x.get("published_at"),updated_at=x.get("updated_at"),publisher=x.get("publisher"),cited_source=x.get("cited_source"),source_kind=SourceKind(x.get("source_kind","unknown")),issuer_hint=x.get("issuer_hint"),document_type_hint=x.get("document_type_hint"),retrieval_purposes=list(x.get("retrieval_purposes",[])),retrieval_claim_ids=list(x.get("retrieval_claim_ids",[])),search_engine=x.get("search_engine")) for x in cached.get("items",[])]
        self.calls+=1;items=list(self.inner.search(query,limit));self.cache.set(key,{"items":[{"url":x.url,"title":x.title,"snippet":x.snippet,"published_at":x.published_at,"updated_at":x.updated_at,"publisher":x.publisher,"cited_source":x.cited_source,"source_kind":x.source_kind.value,"issuer_hint":x.issuer_hint,"document_type_hint":x.document_type_hint,"retrieval_purposes":x.retrieval_purposes,"retrieval_claim_ids":x.retrieval_claim_ids,"search_engine":x.search_engine} for x in items]});return items
class CachedFetcher:
    def __init__(self,inner,cache:CacheBackend,ttl_seconds:int=600)->None:self.inner=inner;self.cache=cache;self.ttl_seconds=max(0,int(ttl_seconds));self.hits=0;self.calls=0;self.bypass_cache=False
    @property
    def stats(self):return {"cache_hits":self.hits,"provider_calls":self.calls,"ttl_seconds":self.ttl_seconds}
    def fetch_text(self,url:str,max_chars:int,relevance_terms:str|None=None)->str:
        key=f"fetch:v3:{max_chars}:{fingerprint(url+'|'+(relevance_terms or ''))}"
        if not self.bypass_cache and self.ttl_seconds>0:
            cached=self.cache.get(key,self.ttl_seconds)
            if cached:self.hits+=1;return str(cached.get("text",""))
        self.calls+=1;text=self.inner.fetch_text(url,max_chars,relevance_terms);self.cache.set(key,{"text":text});return text
