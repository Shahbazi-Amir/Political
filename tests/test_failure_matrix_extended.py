from __future__ import annotations

import json
import threading
from email.message import Message
from pathlib import Path
from unittest.mock import patch

import pytest

from political_core.cache import SQLiteCache
from political_core.fetch import SafeHttpFetcher
from political_core.search_searxng import SearxNGSearchProvider


class SearchHeaders:
    def __init__(self,ctype="application/json"):self.ctype=ctype
    def get(self,key,default=None):return self.ctype if key.lower()=="content-type" else default
class SearchResp:
    def __init__(self,payload,ctype="application/json"):self.payload=payload;self.headers=SearchHeaders(ctype)
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.payload[:n] if n>=0 else self.payload


def test_searx_malformed_json_fails_closed():
    with patch("political_core.search_searxng.urlopen",return_value=SearchResp(b"{broken")):
        with pytest.raises(RuntimeError,match="invalid JSON"):
            SearxNGSearchProvider("https://search.example").search("q",5)


def test_searx_non_json_mime_fails_closed():
    payload=json.dumps({"results":[]}).encode()
    with patch("political_core.search_searxng.urlopen",return_value=SearchResp(payload,"text/html")):
        with pytest.raises(RuntimeError,match="content type"):
            SearxNGSearchProvider("https://search.example").search("q",5)


def _headers(ctype="text/plain"):
    h=Message();h["Content-Type"]=ctype;return h


def test_fetch_redirect_to_private_ip_is_rejected_before_second_request():
    fetcher=SafeHttpFetcher(max_redirects=3);calls=[]
    def once(url):
        calls.append(url);return 302,_headers(),b"","http://127.0.0.1/admin"
    with patch.object(fetcher,"_request_once",side_effect=once):
        with pytest.raises(ValueError):fetcher.fetch_text("https://public.example/x",1000)
    assert calls==["https://public.example/x"]


def test_fetch_redirect_loop_is_bounded():
    fetcher=SafeHttpFetcher(max_redirects=2)
    with patch.object(fetcher,"_request_once",return_value=(302,_headers(),b"","/same")):
        with patch("political_core.fetch.validate_public_url",return_value={"93.184.216.34"}):
            with pytest.raises(RuntimeError,match="too many redirects"):fetcher.fetch_text("https://public.example/same",1000)


def test_fetch_binary_like_payload_is_rejected():
    fetcher=SafeHttpFetcher()
    with patch.object(fetcher,"_request_once",return_value=(200,_headers("text/plain; charset=utf-8"),b"hello\x00binary",None)):
        with pytest.raises(RuntimeError,match="binary-like"):fetcher.fetch_text("https://public.example/x",1000)


def test_sqlite_cache_concurrent_writes_do_not_lose_rows(tmp_path:Path):
    cache=SQLiteCache(tmp_path/"cache.sqlite3");errors=[]
    def writer(worker:int):
        try:
            for i in range(25):cache.set(f"{worker}:{i}",{"worker":worker,"i":i})
        except Exception as exc:errors.append(exc)
    threads=[threading.Thread(target=writer,args=(n,)) for n in range(4)]
    for t in threads:t.start()
    for t in threads:t.join()
    assert not errors
    for worker in range(4):
        for i in range(25):assert cache.get(f"{worker}:{i}",60)=={"worker":worker,"i":i}
