from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    def __init__(self,path:str|Path=".political-cache.sqlite3",max_rows:int=20_000)->None:
        self.path=str(path);self.max_rows=max(100,int(max_rows));self._writes=0
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS fact_cache(cache_key TEXT PRIMARY KEY,created_at INTEGER NOT NULL,payload TEXT NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fact_cache_created ON fact_cache(created_at)")

    def _connect(self)->sqlite3.Connection:
        conn=sqlite3.connect(self.path,timeout=5.0)
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def get(self,key:str,ttl_seconds:int)->dict[str,Any]|None:
        with self._connect() as conn:row=conn.execute("SELECT created_at,payload FROM fact_cache WHERE cache_key=?",(key,)).fetchone()
        if not row:return None
        created,payload=row
        if int(time.time())-int(created)>ttl_seconds:self.delete(key);return None
        try:return json.loads(payload)
        except (json.JSONDecodeError,TypeError,ValueError):
            self.delete(key);return None

    def set(self,key:str,payload:dict[str,Any])->None:
        encoded=json.dumps(payload,ensure_ascii=False,separators=(",",":"))
        with self._connect() as conn:conn.execute("INSERT OR REPLACE INTO fact_cache(cache_key,created_at,payload) VALUES(?,?,?)",(key,int(time.time()),encoded))
        self._writes+=1
        if self._writes%100==0:self.prune()

    def delete(self,key:str)->None:
        with self._connect() as conn:conn.execute("DELETE FROM fact_cache WHERE cache_key=?",(key,))

    def prune(self)->int:
        with self._connect() as conn:
            count=int(conn.execute("SELECT COUNT(*) FROM fact_cache").fetchone()[0]);extra=max(0,count-self.max_rows)
            if extra:
                conn.execute("DELETE FROM fact_cache WHERE cache_key IN (SELECT cache_key FROM fact_cache ORDER BY created_at ASC LIMIT ?)",(extra,))
            return extra
