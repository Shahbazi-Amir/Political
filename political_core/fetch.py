from __future__ import annotations

import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.error import HTTPError,URLError
from urllib.parse import urljoin,urlsplit
from urllib.request import HTTPRedirectHandler,Request,build_opener

from .text import token_set


class _TextExtractor(HTMLParser):
    SKIP={"script","style","noscript","svg","nav","footer","header","form","aside","iframe"}
    BREAK={"p","br","li","h1","h2","h3","h4","blockquote","article","section","div","tr"}
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self._skip=0
    def handle_starttag(self,tag,attrs):
        if tag in self.SKIP:self._skip+=1
        elif not self._skip and tag in self.BREAK:self.parts.append("\n")
    def handle_endtag(self,tag):
        if tag in self.SKIP and self._skip:self._skip-=1
        elif not self._skip and tag in self.BREAK:self.parts.append("\n")
    def handle_data(self,data):
        if not self._skip:self.parts.append(data)
    def text(self):
        joined=html.unescape(" ".join(self.parts))
        joined=re.sub(r"[ \t]+"," ",joined)
        return re.sub(r"\n\s*\n+","\n",joined).strip()


def resolve_public_addresses(host:str,port:int)->set[str]:
    try:
        addresses={item[4][0] for item in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve host: {host}") from exc
    if not addresses:raise ValueError("host resolves to no addresses")
    for raw in addresses:
        ip=ipaddress.ip_address(raw)
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified):
            raise ValueError("refusing private or non-public network address")
    return addresses


def validate_public_url(url:str)->set[str]:
    parts=urlsplit(url)
    if parts.scheme not in {"http","https"} or not parts.hostname:
        raise ValueError("only public http(s) URLs are allowed")
    if parts.username or parts.password:
        raise ValueError("URL userinfo is not allowed")
    host=parts.hostname
    if host.casefold() in {"localhost","localhost.localdomain"} or host.endswith(".local"):
        raise ValueError("local hostnames are forbidden")
    try:
        ip=ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise ValueError("refusing private literal IP")
    except ValueError as exc:
        if "private literal" in str(exc):raise
    port=parts.port or (443 if parts.scheme=="https" else 80)
    return resolve_public_addresses(host,port)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self,max_redirects:int=4):
        super().__init__();self.max_redirects=max_redirects;self.count=0
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.count+=1
        if self.count>self.max_redirects:
            raise HTTPError(req.full_url,code,"too many redirects",headers,fp)
        target=urljoin(req.full_url,newurl)
        validate_public_url(target)
        return super().redirect_request(req,fp,code,msg,headers,target)


class SafeHttpFetcher:
    ALLOWED_TYPES=("text/html","application/xhtml+xml","text/plain","application/json")
    def __init__(self,timeout:float=8.0,max_bytes:int=1_500_000,max_redirects:int=4):
        self.timeout=timeout;self.max_bytes=max_bytes;self.max_redirects=max_redirects

    @staticmethod
    def _relevant_passages(text:str,relevance_terms:str|None,max_chars:int)->str:
        if not relevance_terms or len(text)<=max_chars:return text[:max_chars]
        wanted=token_set(relevance_terms)
        chunks=[x.strip() for x in re.split(r"(?<=[.!?؟\n])\s+",text) if x.strip()]
        ranked=[]
        for idx,chunk in enumerate(chunks):
            score=len(token_set(chunk)&wanted)
            ranked.append((score,-idx,chunk))
        picked=[c for s,_,c in sorted(ranked,reverse=True) if s>0][:24]
        if not picked:return text[:max_chars]
        chosen=set(picked)
        ordered=[c for c in chunks if c in chosen]
        return "\n".join(ordered)[:max_chars]

    def fetch_text(self,url:str,max_chars:int,relevance_terms:str|None=None)->str:
        before=validate_public_url(url)
        redirect=_SafeRedirectHandler(self.max_redirects)
        opener=build_opener(redirect)
        req=Request(url,headers={
            "User-Agent":"PoliticalCore/0.3 (+evidence-fetcher)",
            "Accept":"text/html,application/xhtml+xml,text/plain,application/json;q=0.8",
        })
        try:
            with opener.open(req,timeout=self.timeout) as resp:
                final_url=resp.geturl()
                after=validate_public_url(final_url)
                if urlsplit(final_url).hostname==urlsplit(url).hostname and before.isdisjoint(after):
                    raise RuntimeError("DNS resolution changed during request")
                content_type=(resp.headers.get("Content-Type") or "").lower()
                if content_type and not any(t in content_type for t in self.ALLOWED_TYPES):
                    raise RuntimeError(f"unsupported content type: {content_type}")
                raw=resp.read(self.max_bytes+1)
                if len(raw)>self.max_bytes:raise RuntimeError("response exceeds configured size limit")
                charset=resp.headers.get_content_charset() or "utf-8"
        except (HTTPError,URLError,TimeoutError) as exc:
            raise RuntimeError(f"fetch failed for {url}: {exc}") from exc
        text=raw.decode(charset,errors="replace")
        if "\x00" in text[:500]:raise RuntimeError("binary-like content rejected")
        if "html" in content_type or "<html" in text[:500].lower():
            parser=_TextExtractor();parser.feed(text);text=parser.text()
        text=re.sub(r"[ \t]+"," ",text)
        text=re.sub(r"\n\s*\n+","\n",text).strip()
        return self._relevant_passages(text,relevance_terms,max_chars)
