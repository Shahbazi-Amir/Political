from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from political_core.search_searxng import SearxNGSearchProvider


class Headers:
    def __init__(self,ctype="application/json"):self.ctype=ctype
    def get(self,key,default=None):return self.ctype if key.lower()=="content-type" else default
class Resp:
    def __init__(self,payload,ctype="application/json"):self.payload=payload;self.headers=Headers(ctype)
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n=-1):return self.payload[:n] if n>=0 else self.payload


def test_searx_engine_is_not_treated_as_publisher_or_cited_source():
    payload=json.dumps({"results":[{"url":"https://news.example/story","title":"Story","content":"Text","engine":"google","source":"Reuters"}]}).encode()
    with patch("political_core.search_searxng.urlopen",return_value=Resp(payload)):
        item=SearxNGSearchProvider("https://search.example").search("q",5)[0]
    assert item.publisher=="news.example";assert item.cited_source is None;assert item.search_engine=="google"


def test_searx_response_size_is_bounded():
    payload=b"x"*101
    with patch("political_core.search_searxng.urlopen",return_value=Resp(payload)):
        with pytest.raises(RuntimeError):SearxNGSearchProvider("https://search.example",max_response_bytes=100).search("q",5)
