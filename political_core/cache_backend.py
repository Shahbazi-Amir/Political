from __future__ import annotations
import json,time
from collections import OrderedDict
from copy import deepcopy
from typing import Any,Protocol

class CacheBackend(Protocol):
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:...
    def set(self,key:str,payload:dict[str,Any])->None:...
    def delete(self,key:str)->None:...
class NamespacedCache:
    def __init__(self,inner:CacheBackend,namespace:str)->None:self.inner=inner;self.namespace=namespace.strip(":") or "default"
    def _key(self,key:str)->str:return f"{self.namespace}:{key}"
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:return self.inner.get(self._key(key),ttl_seconds)
    def set(self,key:str,payload:dict[str,Any])->None:self.inner.set(self._key(key),payload)
    def delete(self,key:str)->None:self.inner.delete(self._key(key))
class MemoryCache:
    def __init__(self,max_entries:int=1000)->None:self.max_entries=max(1,int(max_entries));self._rows:OrderedDict[str,tuple[float,dict[str,Any]]]=OrderedDict()
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        row=self._rows.get(key)
        if row is None:return None
        created,payload=row
        if time.time()-created>max(0,ttl_seconds):self.delete(key);return None
        self._rows.move_to_end(key);return deepcopy(payload)
    def set(self,key:str,payload:dict[str,Any])->None:
        self._rows[key]=(time.time(),deepcopy(payload));self._rows.move_to_end(key)
        while len(self._rows)>self.max_entries:self._rows.popitem(last=False)
    def delete(self,key:str)->None:self._rows.pop(key,None)
    def __len__(self)->int:return len(self._rows)
class RedisCache:
    def __init__(self,url:str|None=None,*,client=None,key_prefix:str="political")->None:
        self.key_prefix=key_prefix.strip(":") or "political"
        if client is None:
            if not url:raise RuntimeError("REDIS_URL is required when CACHE_BACKEND=redis")
            try:import redis
            except ImportError as exc:raise RuntimeError("redis backend selected but redis package is not installed; install political-core[redis]") from exc
            client=redis.Redis.from_url(url,decode_responses=True)
        self.client=client
    def _key(self,key:str)->str:return f"{self.key_prefix}:{key}"
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        raw=self.client.get(self._key(key))
        if raw is None:return None
        if isinstance(raw,bytes):raw=raw.decode("utf-8")
        try:envelope=json.loads(raw);created=float(envelope["created_at"]);payload=envelope["payload"]
        except (TypeError,ValueError,KeyError,json.JSONDecodeError):self.delete(key);return None
        if time.time()-created>max(0,int(ttl_seconds)):self.delete(key);return None
        return payload if isinstance(payload,dict) else None
    def set(self,key:str,payload:dict[str,Any])->None:self.client.set(self._key(key),json.dumps({"created_at":time.time(),"payload":payload},ensure_ascii=False,separators=(",",":")))
    def delete(self,key:str)->None:self.client.delete(self._key(key))
def build_cache_backend(kind:str="sqlite",*,sqlite_path:str=".political-cache.sqlite3",max_rows:int=20_000,redis_url:str|None=None,redis_client=None)->CacheBackend:
    kind=(kind or "sqlite").casefold().strip()
    if kind=="sqlite":
        from .cache import SQLiteCache
        return SQLiteCache(sqlite_path,max_rows)
    if kind=="redis":return RedisCache(redis_url,client=redis_client)
    if kind=="memory":return MemoryCache(max_entries=max_rows)
    raise ValueError(f"unsupported CACHE_BACKEND: {kind}")
