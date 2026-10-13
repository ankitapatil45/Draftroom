"""Web search and guarded retrieval of public result pages."""
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

from .config import settings


def _is_public_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return False
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            records = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
            addresses = {ipaddress.ip_address(record[4][0]) for record in records}
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


def search(query: str, n: int = 6) -> list[dict]:
    if not settings.enable_web:
        return []
    try:
        if settings.tavily_api_key:
            r = httpx.post("https://api.tavily.com/search", timeout=20,
                           json={"api_key": settings.tavily_api_key, "query": query, "max_results": n,
                                 "search_depth": "advanced"})
            r.raise_for_status()
            return [{"title": x["title"], "url": x["url"], "snippet": x.get("content", "")[:900]}
                    for x in r.json().get("results", [])]
        from ddgs import DDGS

        with DDGS() as d:
            return [{"title": x["title"], "url": x["href"], "snippet": x.get("body", "")[:900]}
                    for x in d.text(query, max_results=n)]
    except Exception:
        return []


def fetch_text(url: str, limit: int = 2500) -> str:
    try:
        from bs4 import BeautifulSoup

        current_url = url
        with httpx.Client(timeout=15, follow_redirects=False,
                          headers={"User-Agent": "Draftroom/1.0"}) as client:
            for _ in range(4):
                if not _is_public_http_url(current_url):
                    return ""
                r = client.get(current_url)
                if r.is_redirect:
                    location = r.headers.get("location")
                    if not location:
                        return ""
                    current_url = urljoin(current_url, location)
                    continue
                r.raise_for_status()
                break
            else:
                return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer", "header", "aside"]):
            t.decompose()
        return re.sub(r"\s+", " ", soup.get_text(" "))[:limit]
    except Exception:
        return ""
