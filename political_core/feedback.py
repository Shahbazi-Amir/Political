from __future__ import annotations
import sqlite3,time
from pathlib import Path
class FeedbackStore:
    def __init__(self,path:str|Path="political_feedback.sqlite3")->None:
        self.path=str(path)
        with sqlite3.connect(self.path) as conn:conn.execute("""CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,result_id TEXT,claim TEXT,feedback_type TEXT,comment TEXT,created_at INTEGER NOT NULL)""")
    def add(self,result_id:str,claim:str,feedback_type:str,comment:str="")->None:
        allowed={"correct","wrong","partially_wrong","bad_source","missed_source","bad_verdict","bad_reasoning","outdated"}
        if feedback_type not in allowed:raise ValueError("unsupported feedback type")
        with sqlite3.connect(self.path) as conn:conn.execute("INSERT INTO feedback(result_id,claim,feedback_type,comment,created_at) VALUES(?,?,?,?,?)",(result_id,claim,feedback_type,comment,int(time.time())))
