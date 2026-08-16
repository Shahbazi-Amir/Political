from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import SearchResult
from .text import domain_of


class SearxNGSearchProvider:
    def __init__(self,base_url:str,timeout:float=8.0,max_response_bytes:int=2_000_000)->None:
        self.base_url=base_url.rstrip("/");self.timeout=timeout;self.max_response_bytes=max(1,int(max_response_bytes))

    def search(self,query:str,limit:int):
        params=urlencode({"q":query,"format":"json","language":"all","safesearch":"0"})
        req=Request(f"{self.base_url}/search?{params}",headers={"Accept":"application/json","User-Agent":"PoliticalCore/0.4"})
        with urlopen(req,timeout=self.timeout) as resp:
            ctype=(resp.headers.get("Content-Type") or "").casefold()
            if ctype and "json" not in ctype:raise RuntimeError(f"SearxNG returned unsupported content type: {ctype}")
            raw=resp.read(self.max_response_bytes+1)
            if len(raw)>self.max_response_bytes:raise RuntimeError("SearxNG response exceeds configured size limit")
            try:payload=json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise RuntimeError("SearxNG returned invalid JSON") from exc
        out=[]
        for item in payload.get("results",[])[:limit]:
            url=str(item.get("url","")).strip()
            if not url:continue
            out.append(SearchResult(url=url,title=str(item.get("title","")),snippet=str(item.get("content","")),published_at=item.get("publishedDate") or item.get("published_at"),publisher=domain_of(url),cited_source=None,search_engine=str(item.get("engine") or "") or None))
        return out
