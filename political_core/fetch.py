from __future__ import annotations

import html
import http.client
import ipaddress
import re
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit,urlunsplit

from .text import token_set


class _TextExtractor(HTMLParser):
    SKIP={"script","style","noscript","svg","nav","footer","header","form","aside","iframe"};BREAK={"p","br","li","h1","h2","h3","h4","blockquote","article","section","div","tr"}
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self._skip=0
    def handle_starttag(self,tag,attrs):
        if tag in self.SKIP:self._skip+=1
        elif not self._skip and tag in self.BREAK:self.parts.append("\n")
    def handle_endtag(self,tag):
        if tag in self.SKIP and self._skip:self._skip-=1
        elif not self._skip and tag in self.BREAK:self.parts.append("\n")
    def handle_data(self,data):
        if not self._skip:self.parts.append(data)
    def text(self):
        joined=html.unescape(" ".join(self.parts));joined=re.sub(r"[ \t]+"," ",joined);return re.sub(r"\n\s*\n+","\n",joined).strip()


def resolve_public_addresses(host:str,port:int)->set[str]:
    try:addresses={item[4][0] for item in socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:raise ValueError(f"cannot resolve host: {host}") from exc
    if not addresses:raise ValueError("host resolves to no addresses")
    for raw in addresses:
        ip=ipaddress.ip_address(raw)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:raise ValueError("refusing private or non-public network address")
    return addresses


def validate_public_url(url:str)->set[str]:
    parts=urlsplit(url)
    if parts.scheme not in {"http","https"} or not parts.hostname:raise ValueError("only public http(s) URLs are allowed")
    if parts.username or parts.password:raise ValueError("URL userinfo is not allowed")
    host=parts.hostname
    if host.casefold() in {"localhost","localhost.localdomain"} or host.endswith(".local"):raise ValueError("local hostnames are forbidden")
    try:
        ip=ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:raise ValueError("refusing private literal IP")
    except ValueError as exc:
        if "private literal" in str(exc):raise
    port=parts.port or (443 if parts.scheme=="https" else 80)
    return resolve_public_addresses(host,port)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self,host:str,pinned_ip:str,port:int,timeout:float):
        self._pinned_ip=pinned_ip;super().__init__(host,port=port,timeout=timeout)
    def connect(self):
        self.sock=socket.create_connection((self._pinned_ip,self.port),self.timeout,self.source_address)
        if self._tunnel_host:self._tunnel()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,host:str,pinned_ip:str,port:int,timeout:float):
        self._pinned_ip=pinned_ip;super().__init__(host,port=port,timeout=timeout,context=ssl.create_default_context())
    def connect(self):
        sock=socket.create_connection((self._pinned_ip,self.port),self.timeout,self.source_address)
        if self._tunnel_host:
            self.sock=sock;self._tunnel();sock=self.sock
        server_hostname=self._tunnel_host or self.host
        self.sock=self._context.wrap_socket(sock,server_hostname=server_hostname)


class SafeHttpFetcher:
    ALLOWED_TYPES=("text/html","application/xhtml+xml","text/plain","application/json")
    def __init__(self,timeout:float=8.0,max_bytes:int=1_500_000,max_redirects:int=4):self.timeout=timeout;self.max_bytes=max_bytes;self.max_redirects=max_redirects

    @staticmethod
    def _relevant_passages(text:str,relevance_terms:str|None,max_chars:int)->str:
        if not relevance_terms or len(text)<=max_chars:return text[:max_chars]
        wanted=token_set(relevance_terms);chunks=[x.strip() for x in re.split(r"(?<=[.!?؟\n])\s+",text) if x.strip()];ranked=[]
        for idx,chunk in enumerate(chunks):ranked.append((len(token_set(chunk)&wanted),-idx,chunk))
        picked=[c for s,_,c in sorted(ranked,reverse=True) if s>0][:24]
        if not picked:return text[:max_chars]
        chosen=set(picked);return "\n".join(c for c in chunks if c in chosen)[:max_chars]

    @staticmethod
    def _path(parts)->str:
        return urlunsplit(("","",parts.path or "/",parts.query,""))

    def _request_once(self,url:str):
        parts=urlsplit(url);host=parts.hostname or "";port=parts.port or (443 if parts.scheme=="https" else 80);addresses=validate_public_url(url)
        last=None
        for ip in sorted(addresses,key=lambda x:(":" in x,x)):
            conn=None
            try:
                cls=_PinnedHTTPSConnection if parts.scheme=="https" else _PinnedHTTPConnection;conn=cls(host,ip,port,self.timeout)
                conn.request("GET",self._path(parts),headers={"User-Agent":"PoliticalCore/0.4 (+evidence-fetcher)","Accept":"text/html,application/xhtml+xml,text/plain,application/json;q=0.8","Connection":"close"})
                resp=conn.getresponse();status=resp.status;headers=resp.headers
                location=headers.get("Location")
                if 300<=status<400:
                    return status,headers,b"",location
                if status>=400:raise RuntimeError(f"HTTP status {status}")
                content_type=(headers.get("Content-Type") or "").lower()
                if content_type and not any(t in content_type for t in self.ALLOWED_TYPES):raise RuntimeError(f"unsupported content type: {content_type}")
                raw=resp.read(self.max_bytes+1)
                if len(raw)>self.max_bytes:raise RuntimeError("response exceeds configured size limit")
                return status,headers,raw,None
            except (OSError,ssl.SSLError,http.client.HTTPException,RuntimeError) as exc:last=exc
            finally:
                if conn:
                    try:conn.close()
                    except Exception:pass
        raise RuntimeError(f"fetch failed for {url}: {last}")

    def fetch_text(self,url:str,max_chars:int,relevance_terms:str|None=None)->str:
        current=url
        for redirects in range(self.max_redirects+1):
            status,headers,raw,location=self._request_once(current)
            if 300<=status<400:
                if not location:raise RuntimeError("redirect missing Location header")
                if redirects>=self.max_redirects:raise RuntimeError("too many redirects")
                current=urljoin(current,location);validate_public_url(current);continue
            content_type=(headers.get("Content-Type") or "").lower();charset=headers.get_content_charset() or "utf-8";text=raw.decode(charset,errors="replace")
            if "\x00" in text[:500]:raise RuntimeError("binary-like content rejected")
            if "html" in content_type or "<html" in text[:500].lower():parser=_TextExtractor();parser.feed(text);text=parser.text()
            text=re.sub(r"[ \t]+"," ",text);text=re.sub(r"\n\s*\n+","\n",text).strip();return self._relevant_passages(text,relevance_terms,max_chars)
        raise RuntimeError("too many redirects")
