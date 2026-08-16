from __future__ import annotations
import json,time
from collections import OrderedDict
from copy import deepcopy
from typing import Any,Protocol

class CacheBackend(Protocol):
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:...
    def set(self,key:str,payload:dict[str,Any],ttl_seconds:int|None=None)->None:...
    def delete(self,key:str)->None:...

class NamespacedCache:
    def __init__(self,inner:CacheBackend,namespace:str)->None:self.inner=inner;self.namespace=namespace.strip(":") or "default"
    def _key(self,key:str)->str:return f"{self.namespace}:{key}"
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:return self.inner.get(self._key(key),ttl_seconds)
    def set(self,key:str,payload:dict[str,Any],ttl_seconds:int|None=None)->None:self.inner.set(self._key(key),payload,ttl_seconds)
    def delete(self,key:str)->None:self.inner.delete(self._key(key))

class MemoryCache:
    def __init__(self,max_entries:int=1000)->None:self.max_entries=max(1,int(max_entries));self._rows:OrderedDict[str,tuple[float,dict[str,Any]]]=OrderedDict()
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        row=self._rows.get(key)
        if row is None:return None
        created,payload=row
        if time.time()-created>max(0,ttl_seconds):self.delete(key);return None
        self._rows.move_to_end(key);return deepcopy(payload)
    def set(self,key:str,payload:dict[str,Any],ttl_seconds:int|None=None)->None:
        self._rows[key]=(time.time(),deepcopy(payload));self._rows.move_to_end(key)
        while len(self._rows)>self.max_entries:self._rows.popitem(last=False)
    def delete(self,key:str)->None:self._rows.pop(key,None)
    def __len__(self)->int:return len(self._rows)

class RedisCache:
    def __init__(self,url:str|None=None,*,client=None,key_prefix:str="political",default_ttl_seconds:int=21600)->None:
        self.key_prefix=key_prefix.strip(":") or "political";self.default_ttl_seconds=max(1,int(default_ttl_seconds))
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
    def set(self,key:str,payload:dict[str,Any],ttl_seconds:int|None=None)->None:
        ttl=max(1,int(ttl_seconds or self.default_ttl_seconds));value=json.dumps({"created_at":time.time(),"payload":payload},ensure_ascii=False,separators=(",",":"))
        try:self.client.set(self._key(key),value,ex=ttl)
        except TypeError:self.client.set(self._key(key),value)  # small test doubles may not expose EX
    def delete(self,key:str)->None:self.client.delete(self._key(key))

class ResilientCache:
    """Fail-open cache wrapper. Verification continues if the cache backend is unavailable."""
    def __init__(self,inner:CacheBackend,*,fail_open:bool=True)->None:self.inner=inner;self.fail_open=fail_open;self.errors=[]
    def _error(self,op:str,exc:Exception):
        self.errors.append(f"{op}:{type(exc).__name__}")
        if len(self.errors)>100:self.errors=self.errors[-100:]
        if not self.fail_open:raise exc
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        try:return self.inner.get(key,ttl_seconds)
        except Exception as exc:self._error("get",exc);return None
    def set(self,key:str,payload:dict[str,Any],ttl_seconds:int|None=None)->None:
        try:
            try:self.inner.set(key,payload,ttl_seconds)
            except TypeError:self.inner.set(key,payload)
        except Exception as exc:self._error("set",exc)
    def delete(self,key:str)->None:
        try:self.inner.delete(key)
        except Exception as exc:self._error("delete",exc)

def build_cache_backend(kind:str="sqlite",*,sqlite_path:str=".political-cache.sqlite3",max_rows:int=20_000,redis_url:str|None=None,redis_client=None,fail_open:bool=True,redis_default_ttl:int=21600)->CacheBackend:
    kind=(kind or "sqlite").casefold().strip()
    if kind=="sqlite":
        from .cache import SQLiteCache
        raw=SQLiteCache(sqlite_path,max_rows)
    elif kind=="redis":raw=RedisCache(redis_url,client=redis_client,default_ttl_seconds=redis_default_ttl)
    elif kind=="memory":raw=MemoryCache(max_entries=max_rows)
    else:raise ValueError(f"unsupported CACHE_BACKEND: {kind}")
    return ResilientCache(raw,fail_open=fail_open)
