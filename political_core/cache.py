from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, created REAL NOT NULL, value TEXT NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def get(self, key: str, ttl_seconds: int) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT created, value FROM cache WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        created, payload = row
        if ttl_seconds >= 0 and time.time() - created > ttl_seconds:
            with self._connect() as con:
                con.execute("DELETE FROM cache WHERE key = ?", (key,))
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as con:
            con.execute("INSERT OR REPLACE INTO cache(key, created, value) VALUES(?,?,?)", (key, time.time(), payload))
