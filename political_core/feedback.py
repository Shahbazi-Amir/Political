from __future__ import annotations

import sqlite3,time
from pathlib import Path

from .text import fingerprint


class FeedbackStore:
    def __init__(self,path:str|Path="political_feedback.sqlite3",*,store_user_content:bool=False)->None:
        self.path=str(path);self.store_user_content=store_user_content
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,result_id TEXT,claim TEXT,claim_hash TEXT,feedback_type TEXT,comment TEXT,created_at INTEGER NOT NULL)")
            cols={row[1] for row in conn.execute("PRAGMA table_info(feedback)")}
            if "claim_hash" not in cols:conn.execute("ALTER TABLE feedback ADD COLUMN claim_hash TEXT")
    def add(self,result_id:str,claim:str,feedback_type:str,comment:str="")->None:
        allowed={"correct","wrong","partially_wrong","bad_source","missed_source","bad_verdict","bad_reasoning","outdated"}
        if feedback_type not in allowed:raise ValueError("unsupported feedback type")
        stored_claim=claim if self.store_user_content else "";stored_comment=comment if self.store_user_content else ""
        with sqlite3.connect(self.path,timeout=5.0) as conn:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("INSERT INTO feedback(result_id,claim,claim_hash,feedback_type,comment,created_at) VALUES(?,?,?,?,?,?)",(result_id,stored_claim,fingerprint(claim),feedback_type,stored_comment,int(time.time())))
