from __future__ import annotations
import json
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from .models import SearchResult
class SearxNGSearchProvider:
    def __init__(self,base_url:str,timeout:float=8.0)->None:self.base_url=base_url.rstrip("/");self.timeout=timeout
    def search(self,query:str,limit:int):
        params=urlencode({"q":query,"format":"json","language":"all","safesearch":"0"});req=Request(f"{self.base_url}/search?{params}",headers={"Accept":"application/json","User-Agent":"PoliticalCore/0.3"})
        with urlopen(req,timeout=self.timeout) as resp:payload=json.loads(resp.read().decode("utf-8"))
        out=[]
        for item in payload.get("results",[])[:limit]:out.append(SearchResult(url=str(item.get("url","")),title=str(item.get("title","")),snippet=str(item.get("content","")),published_at=item.get("publishedDate") or item.get("published_at"),publisher=item.get("engine"),cited_source=item.get("source")))
        return [x for x in out if x.url]
