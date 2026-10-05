"""
Brazilian news headlines from RSS feeds.

WHY THIS EXISTS
    The briefing used to ask a search engine for "notícias de tecnologia". For
    Portuguese queries DuckDuckGo often returns nothing, and the Gemini fallback
    needs text-model quota that a free key does not have. RSS needs neither: a
    news site publishes its latest headlines as a small XML file, in the
    language of the site, newest first.

HOW IT BEHAVES
    * Every feed is fetched in parallel with its own short timeout. One dead
      feed costs nothing but its own headlines.
    * RSS 2.0 and Atom are both read. HTML in summaries is stripped.
    * Items are merged newest first, duplicates dropped, and no single site can
      fill the whole list.
    * The result has the same shape as web_search._format_news(), so every
      consumer of that text (the briefing, the on-screen panel) works unchanged.
    * Returns "No news found for: ..." when nothing could be read, which is what
      the caller already treats as "try the next backend".

EDITING THE FEEDS
    Change FEEDS below. A feed that moves or disappears is logged and skipped.
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# (site name, feed URL). Edit freely.
FEEDS: dict[str, list[tuple[str, str]]] = {
    "tecnologia": [
        ("G1 Tecnologia", "https://g1.globo.com/rss/g1/tecnologia/"),
        ("Olhar Digital", "https://olhardigital.com.br/feed/"),
        ("Canaltech",     "https://canaltech.com.br/rss/"),
    ],
    "brasil": [
        ("G1",            "https://g1.globo.com/rss/g1/"),
        ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml"),
        ("Folha",         "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml"),
    ],
}

_TIMEOUT_PER_FEED = 4.0     # seconds, connect + read
_TOTAL_BUDGET     = 6.0     # seconds for the whole fetch; the briefing waits 8
_MAX_BYTES        = 1_500_000
_PER_FEED_ITEMS   = 4       # so one site cannot fill the list
_MAX_AGE_DAYS     = 4       # older than this is not "today's news"
_USER_AGENT       = "Mozilla/5.0 (X11; Linux x86_64) JARVIS-news/1.0"

_TAG_RE   = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_CTRL_RE  = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(text: str | None, limit: int = 0) -> str:
    """Plain one-line text: no tags, entities decoded, no control characters."""
    if not text:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", text))
    text = _CTRL_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text[:limit].rstrip() if limit else text


def _local(tag: str) -> str:
    """Tag name without its XML namespace: '{ns}title' -> 'title'."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child_text(node: ET.Element, *names: str) -> str:
    for child in node:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text.strip()
    return ""


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    try:                                    # RSS: RFC 822
        dt = parsedate_to_datetime(raw)
    except Exception:
        try:                                # Atom: ISO 8601
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _atom_link(node: ET.Element) -> str:
    for child in node:
        if _local(child.tag) == "link":
            href = child.get("href")
            if href and child.get("rel", "alternate") == "alternate":
                return href
    return ""


def parse_feed(xml_bytes: bytes, source: str) -> list[dict]:
    """Items of an RSS 2.0 or Atom document, as dicts. [] if it is neither."""
    # ElementTree expands entities, so a hostile document could balloon in
    # memory. A news feed never needs a DTD or custom entities; refuse them.
    head = xml_bytes[:4096].lower()
    if b"<!entity" in xml_bytes.lower() or b"<!doctype" in head and b"[" in head:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    items = []
    for node in root.iter():
        kind = _local(node.tag)
        if kind not in ("item", "entry"):
            continue
        title = _clean(_child_text(node, "title"), 160)
        if not title:
            continue
        link = (_child_text(node, "link") if kind == "item" else _atom_link(node))
        summary = _clean(
            _child_text(node, "description", "summary", "content", "encoded"), 140)
        when = _parse_date(
            _child_text(node, "pubDate", "published", "updated", "date"))
        items.append({
            "title": title, "url": _clean(link), "snippet": summary,
            "source": source, "date": when,
        })
    return items


def _fetch_one(name: str, url: str) -> list[dict]:
    import requests

    try:
        resp = requests.get(
            url, timeout=_TIMEOUT_PER_FEED, stream=True,
            headers={"User-Agent": _USER_AGENT,
                     "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        )
        resp.raise_for_status()
        body = resp.raw.read(_MAX_BYTES + 1, decode_content=True)
        if len(body) > _MAX_BYTES:
            print(f"[NewsRSS] {name}: feed larger than {_MAX_BYTES} bytes, skipped")
            return []
        items = parse_feed(body, name)
        if not items:
            print(f"[NewsRSS] {name}: no readable items")
        return items
    except Exception as e:
        print(f"[NewsRSS] {name}: {type(e).__name__}: {str(e)[:100]}")
        return []


def _key(title: str) -> str:
    return re.sub(r"\W+", "", title.lower())[:60]


def _format(topic: str, items: list[dict]) -> str:
    if not items:
        return f"No news found for: {topic}"
    lines = [f"Latest news: {topic}\n"]
    for i, r in enumerate(items, 1):
        lines.append(f"{i}. {r['title']}  [{r['source']}]")
        if r["snippet"] and r["snippet"].lower() != r["title"].lower():
            lines.append(f"   {r['snippet']}")
        if r["url"]:
            lines.append(f"   {r['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def fetch_news(topic: str = "tecnologia", limit: int = 8) -> str:
    """Latest headlines for `topic` ('tecnologia' or 'brasil'), newest first."""
    feeds = FEEDS.get(topic.lower().strip())
    if not feeds:
        return f"No news found for: {topic}"

    pool = ThreadPoolExecutor(max_workers=len(feeds), thread_name_prefix="rss")
    futures = [pool.submit(_fetch_one, n, u) for n, u in feeds]
    done, _late = wait(futures, timeout=_TOTAL_BUDGET)
    pool.shutdown(wait=False, cancel_futures=True)      # never block the caller

    now = datetime.now(timezone.utc)
    oldest_ok = now.timestamp() - _MAX_AGE_DAYS * 86400
    floor = datetime.fromtimestamp(0, timezone.utc)

    picked: list[dict] = []
    for fut in done:
        try:
            items = fut.result()
        except Exception:
            continue
        # Newest first inside the feed, a few per site, stale items dropped.
        items.sort(key=lambda r: r["date"] or floor, reverse=True)
        fresh = [r for r in items
                 if r["date"] is None or r["date"].timestamp() >= oldest_ok]
        picked.extend(fresh[:_PER_FEED_ITEMS])

    picked.sort(key=lambda r: r["date"] or floor, reverse=True)

    seen: set[str] = set()
    unique = []
    for r in picked:
        k = _key(r["title"])
        if k and k not in seen:
            seen.add(k)
            unique.append(r)

    return _format(topic, unique[:limit])
