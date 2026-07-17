"""Parse and normalize newsletter emails into discrete news items. Deterministic.

Splits each email into items (title, text, source link). Most newsletters are link-driven
digests, so the generic strategy finds outbound links and their surrounding text; an
optional per-sender CSS selector hint (from config) selects item containers when the
generic heuristic is not enough. Each item gets a stable content hash for cross-run dedup.
A narrow LLM fallback for very messy emails is intentionally left as a default-off hook.
See docs/v1-architecture.md (Section 4.2).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

from bs4 import BeautifulSoup

from .ingest.base import RawMessage

# Links whose text or href match these are boilerplate, not news items.
_SKIP = re.compile(
    r"unsubscribe|disiscriv|preferenc|privacy|cookie|view (this|in)|"
    r"in browser|twitter|facebook|linkedin|instagram|mailto:|t\.me/",
    re.IGNORECASE,
)
_HTTP = re.compile(r"^https?://", re.IGNORECASE)
_MIN_TITLE_LEN = 8


@dataclass
class ParsedItem:
    title: str
    text: str
    link: str
    content_hash: str


def _clean(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _hash(title: str, text: str, link: str) -> str:
    norm = _clean(f"{title} {text} {link}").lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def extract_bodies(msg: EmailMessage):
    """Return (html, text) bodies, preferring HTML. Either may be None."""
    html = text = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype == "text/html" and html is None:
                html = part.get_content()
            elif ctype == "text/plain" and text is None:
                text = part.get_content()
    else:
        payload = msg.get_content()
        if msg.get_content_type() == "text/html":
            html = payload
        else:
            text = payload
    return html, text


def _make_item(title: str, text: str, link: str) -> ParsedItem:
    title, text, link = _clean(title), _clean(text), link.strip()
    return ParsedItem(title=title, text=text, link=link, content_hash=_hash(title, text, link))


def _parse_html(html: str, parse_hint: Optional[str]) -> list[ParsedItem]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    items: list[ParsedItem] = []
    seen: set[str] = set()

    def consider(title: str, text: str, link: str) -> None:
        if not _HTTP.match(link or "") or link in seen:
            return
        if _SKIP.search(link) or _SKIP.search(title or ""):
            return
        if len(_clean(title)) < _MIN_TITLE_LEN:
            return
        seen.add(link)
        items.append(_make_item(title, text or title, link))

    if parse_hint:
        for block in soup.select(parse_hint):
            a = block.find("a", href=_HTTP)
            if not a:
                continue
            consider(a.get_text(), block.get_text(), a.get("href", ""))
    else:
        for a in soup.find_all("a", href=_HTTP):
            container = a.find_parent(["p", "td", "div", "li", "article", "section"])
            text = container.get_text() if container else a.get_text()
            consider(a.get_text(), text, a.get("href", ""))

    return items


def _parse_text(text: str) -> list[ParsedItem]:
    items: list[ParsedItem] = []
    seen: set[str] = set()
    for block in re.split(r"\n\s*\n", text):
        url_match = re.search(r"https?://\S+", block)
        if not url_match:
            continue
        link = url_match.group(0).rstrip(").,")
        if link in seen or _SKIP.search(link):
            continue
        body = _clean(block)
        title = body[:120]
        if len(title) < _MIN_TITLE_LEN:
            continue
        seen.add(link)
        items.append(_make_item(title, body, link))
    return items


def parse_email(raw_message: RawMessage, parse_hint: Optional[str] = None) -> list[ParsedItem]:
    """Split one raw newsletter message into news items."""
    html, text = extract_bodies(raw_message.message)
    if html:
        items = _parse_html(html, parse_hint)
        if items:
            return items
    if text:
        return _parse_text(text)
    return []
