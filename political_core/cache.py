from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

class SQLiteCache:
    def __init__(self,path:str|Path=".political-cache.sqlite3")->None:
        self.path=str(path)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS fact_cache(cache_key TEXT PRIMARY KEY,created_at INTEGER NOT NULL,payload TEXT NOT NULL)""")
    def _connect(self)->sqlite3.Connection:return sqlite3.connect(self.path)
    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        with self._connect() as conn:row=conn.execute("SELECT created_at,payload FROM fact_cache WHERE cache_key=?",(key,)).fetchone()
        if not row:return None
        created,payload=row
        if int(time.time())-int(created)>ttl_seconds:self.delete(key);return None
        return json.loads(payload)
    def set(self,key:str,payload:dict[str,Any])->None:
        encoded=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
        with self._connect() as conn:conn.execute("INSERT OR REPLACE INTO fact_cache(cache_key,created_at,payload) VALUES(?,?,?)",(key,int(time.time()),encoded))
    def delete(self,key:str)->None:
        with self._connect() as conn:conn.execute("DELETE FROM fact_cache WHERE cache_key=?",(key,))
