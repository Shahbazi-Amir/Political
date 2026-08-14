from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .text import fingerprint


class FeedbackStore:
    def __init__(self, path: str | Path = "political_feedback.sqlite3") -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim_key TEXT NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating BETWEEN -1 AND 1),
                    note TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                )"""
            )

    def add(self, claim: str, rating: int, note: str = "") -> None:
        if rating not in {-1, 0, 1}:
            raise ValueError("rating must be -1, 0, or 1")
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO feedback(claim_key, rating, note, created_at) VALUES (?, ?, ?, ?)",
                (fingerprint(claim), rating, note[:2000], int(time.time())),
            )
