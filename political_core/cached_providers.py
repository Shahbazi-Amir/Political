from __future__ import annotations
from .cache import SQLiteCache
from .models import SearchResult,SourceKind
from .text import fingerprint
class CachedSearchProvider:
    def __init__(self,inner,cache:SQLiteCache,ttl_seconds:int=1800)->None:self.inner=inner;self.cache=cache;self.ttl_seconds=ttl_seconds;self.hits=0;self.calls=0
    @property
    def stats(self):return {"cache_hits":self.hits,"provider_calls":self.calls}
    def search(self,query:str,limit:int):
        key=f"search:v2:{limit}:{fingerprint(query)}";cached=self.cache.get(key,self.ttl_seconds)
        if cached:
            self.hits+=1
            return [SearchResult(url=x["url"],title=x["title"],snippet=x.get("snippet",""),published_at=x.get("published_at"),updated_at=x.get("updated_at"),publisher=x.get("publisher"),cited_source=x.get("cited_source"),source_kind=SourceKind(x.get("source_kind","unknown")),issuer_hint=x.get("issuer_hint"),document_type_hint=x.get("document_type_hint"),retrieval_purposes=list(x.get("retrieval_purposes",[]))) for x in cached.get("items",[])]
        self.calls+=1;items=list(self.inner.search(query,limit))
        self.cache.set(key,{"items":[{"url":x.url,"title":x.title,"snippet":x.snippet,"published_at":x.published_at,"updated_at":x.updated_at,"publisher":x.publisher,"cited_source":x.cited_source,"source_kind":x.source_kind.value,"issuer_hint":x.issuer_hint,"document_type_hint":x.document_type_hint,"retrieval_purposes":x.retrieval_purposes} for x in items]});return items
class CachedFetcher:
    def __init__(self,inner,cache:SQLiteCache,ttl_seconds:int=1800)->None:self.inner=inner;self.cache=cache;self.ttl_seconds=ttl_seconds;self.hits=0;self.calls=0
    @property
    def stats(self):return {"cache_hits":self.hits,"provider_calls":self.calls}
    def fetch_text(self,url:str,max_chars:int,relevance_terms:str|None=None)->str:
        key=f"fetch:v2:{max_chars}:{fingerprint(url+'|'+(relevance_terms or ''))}";cached=self.cache.get(key,self.ttl_seconds)
        if cached:self.hits+=1;return str(cached.get("text",""))
        self.calls+=1;text=self.inner.fetch_text(url,max_chars,relevance_terms);self.cache.set(key,{"text":text});return text
