from __future__ import annotations

import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any, Protocol


class CacheBackend(Protocol):
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None: ...
    def set(self,key:str,payload:dict[str,Any])->None: ...
    def delete(self,key:str)->None: ...


class NamespacedCache:
    """Thin adapter usable with SQLite today and Redis/Postgres-backed adapters later."""
    def __init__(self,inner:CacheBackend,namespace:str)->None:
        self.inner=inner
        self.namespace=namespace.strip(":") or "default"

    def _key(self,key:str)->str:
        return f"{self.namespace}:{key}"

    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        return self.inner.get(self._key(key),ttl_seconds)

    def set(self,key:str,payload:dict[str,Any])->None:
        self.inner.set(self._key(key),payload)

    def delete(self,key:str)->None:
        self.inner.delete(self._key(key))


class MemoryCache:
    """Bounded test/single-process cache implementing the same structural contract."""
    def __init__(self,max_entries:int=1000)->None:
        self.max_entries=max(1,int(max_entries))
        self._rows:OrderedDict[str,tuple[float,dict[str,Any]]]=OrderedDict()

    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        row=self._rows.get(key)
        if row is None:return None
        created,payload=row
        if time.time()-created>max(0,ttl_seconds):
            self.delete(key);return None
        self._rows.move_to_end(key)
        return deepcopy(payload)

    def set(self,key:str,payload:dict[str,Any])->None:
        self._rows[key]=(time.time(),deepcopy(payload));self._rows.move_to_end(key)
        while len(self._rows)>self.max_entries:self._rows.popitem(last=False)

    def delete(self,key:str)->None:
        self._rows.pop(key,None)

    def __len__(self)->int:return len(self._rows)
