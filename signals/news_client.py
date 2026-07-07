"""Fetches recent crypto news headlines from public RSS feeds (no key required)."""
import re
import xml.etree.ElementTree as ET

import requests

FEED_URLS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://www.theblock.co/rss.xml",
)

SYMBOL_KEYWORDS = {
    "BTCUSDT": ("bitcoin", "btc"),
    "ETHUSDT": ("ethereum", "ether", "eth"),
    # PAXG is tokenized gold; GBPUSDT tracks GBP/USD. The feeds are
    # crypto-focused, so matches will be sparse — the engine proceeds
    # without headlines when nothing matches.
    "PAXGUSDT": ("gold", "paxg"),
    "GBPUSDT": ("gbp", "sterling", "pound sterling", "bank of england"),
}


def _titles_from_feed(content: bytes) -> list:
    root = ET.fromstring(content)
    titles = []
    # RSS uses <item><title>; Atom uses namespaced <entry><title>.
    for path in (".//item/title", ".//{*}entry/{*}title"):
        for node in root.findall(path):
            if node.text and node.text.strip():
                titles.append(node.text.strip())
    return titles


def _matches(title: str, keywords: tuple) -> bool:
    # Word boundaries so "eth" doesn't match "together".
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", title, re.IGNORECASE)
        for keyword in keywords
    )


def fetch_headlines(symbol, limit=10, session=None):
    keywords = SYMBOL_KEYWORDS.get(symbol)
    if keywords is None:
        return []
    session = session or requests.Session()
    headlines = []
    failed_feeds = 0
    for url in FEED_URLS:
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            titles = _titles_from_feed(response.content)
        except Exception:
            failed_feeds += 1
            continue
        for title in titles:
            if _matches(title, keywords) and title not in headlines:
                headlines.append(title)
    if failed_feeds == len(FEED_URLS):
        raise RuntimeError("all RSS feeds unavailable")
    return headlines[:limit]
