from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_ALLOWED = {"correct", "wrong", "partially_wrong", "bad_source", "missed_source", "bad_verdict", "bad_reasoning", "outdated"}


class FeedbackStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS feedback(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id TEXT,
                claim TEXT,
                feedback_type TEXT NOT NULL,
                comment TEXT,
                created_at TEXT NOT NULL
            )""")

    def add(self, *, result_id: str, claim: str, feedback_type: str, comment: str = "") -> None:
        if feedback_type not in _ALLOWED:
            raise ValueError(f"unsupported feedback type: {feedback_type}")
        with sqlite3.connect(self.path) as con:
            con.execute("INSERT INTO feedback(result_id,claim,feedback_type,comment,created_at) VALUES(?,?,?,?,?)", (result_id, claim, feedback_type, comment, datetime.now(timezone.utc).isoformat()))
