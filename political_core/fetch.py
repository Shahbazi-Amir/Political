from __future__ import annotations

import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        elif tag in {"p", "br", "li", "h1", "h2", "h3", "blockquote", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        elif tag in {"p", "li", "h1", "h2", "h3", "blockquote", "article", "section"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        joined = html.unescape(" ".join(self.parts))
        joined = re.sub(r"[ \t]+", " ", joined)
        joined = re.sub(r"\n\s*\n+", "\n", joined)
        return joined.strip()


class SafeHttpFetcher:
    def __init__(self, timeout: float = 8.0, max_bytes: int = 1_500_000) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ValueError("only public http(s) URLs are allowed")
        host = parts.hostname
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, parts.port or 443, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise ValueError(f"cannot resolve host: {host}") from exc
        for raw in addresses:
            ip = ipaddress.ip_address(raw)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError("refusing private or non-public network address")

    def fetch_text(self, url: str, max_chars: int) -> str:
        self._validate_public_url(url)
        req = Request(
            url,
            headers={
                "User-Agent": "PoliticalCore/0.1 (+evidence-fetcher)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.2",
            },
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                content_type = (resp.headers.get("Content-Type") or "").lower()
                raw = resp.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raw = raw[: self.max_bytes]
                charset = resp.headers.get_content_charset() or "utf-8"
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"fetch failed for {url}: {exc}") from exc
        text = raw.decode(charset, errors="replace")
        if "html" in content_type or "<html" in text[:500].lower():
            parser = _TextExtractor()
            parser.feed(text)
            text = parser.text()
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
