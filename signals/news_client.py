"""Fetches recent market news headlines from public RSS feeds (no key required)."""
import re
import xml.etree.ElementTree as ET

import requests

FEED_URLS = (
    # Crypto
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://www.theblock.co/rss.xml",
    # Gold + forex, so PAXGUSDT/GBPUSDT confirmation sees real headlines.
    "https://www.fxstreet.com/rss/news",
    "https://www.forexlive.com/feed/news",
)

SYMBOL_KEYWORDS = {
    "BTCUSDT": ("bitcoin", "btc"),
    "ETHUSDT": ("ethereum", "ether", "eth"),
    # PAXG is tokenized gold; GBPUSDT tracks GBP/USD.
    "PAXGUSDT": ("gold", "paxg", "xau"),
    "GBPUSDT": ("gbp", "sterling", "pound sterling", "bank of england", "boe"),
}


def keywords_for_symbol(symbol: str) -> tuple[str, ...]:
    """Keyword set for headline filtering; derives a base-asset token for
    unknown symbols so admin-added markets are not permanently news-blind."""
    known = SYMBOL_KEYWORDS.get(symbol)
    if known is not None:
        return known
    base = symbol.upper()
    for quote in ("USDT", "USD", "BUSD", "USDC"):
        if base.endswith(quote) and len(base) > len(quote):
            base = base[: -len(quote)]
            break
    base = base.lower()
    if len(base) < 2:
        return ()
    return (base,)


def _titles_from_feed(content: bytes) -> list:
    root = ET.fromstring(content)
    titles = []
    # RSS uses <item><title>; Atom uses namespaced <entry><title>.
    for path in (".//item/title", ".//{*}entry/{*}title"):
        for node in root.findall(path):
            if node.text and node.text.strip():
                titles.append(node.text.strip())
    return titles


def _matches(title: str, keywords: tuple, *, prefix_ok: bool = False) -> bool:
    # Word boundaries so "eth" doesn't match "together". Derived unknown-symbol
    # keywords also allow a prefix match so "doge" hits "Dogecoin".
    for keyword in keywords:
        pattern = rf"\b{re.escape(keyword)}" + (r"" if prefix_ok else r"\b")
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False


def fetch_feed_titles(session=None) -> list:
    """All titles from every feed, fetched once. Feeds are independent: one
    broken feed is skipped; raises only when every feed fails."""
    session = session or requests.Session()
    titles = []
    failed_feeds = 0
    for url in FEED_URLS:
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            titles.extend(_titles_from_feed(response.content))
        except Exception:
            failed_feeds += 1
    if failed_feeds == len(FEED_URLS):
        raise RuntimeError("all RSS feeds unavailable")
    return titles


def filter_headlines(titles, symbol, limit=10) -> list:
    """Titles relevant to `symbol` (deduped, first `limit`); [] when no keywords."""
    keywords = keywords_for_symbol(symbol)
    if not keywords:
        return []
    loose = symbol not in SYMBOL_KEYWORDS
    headlines = []
    for title in titles:
        if _matches(title, keywords, prefix_ok=loose) and title not in headlines:
            headlines.append(title)
    return headlines[:limit]


def fetch_headlines(symbol, limit=10, session=None):
    """Fetch + filter in one call. Prefer fetch_feed_titles once per run and
    filter_headlines per symbol when scanning multiple symbols."""
    if not keywords_for_symbol(symbol):
        return []
    return filter_headlines(fetch_feed_titles(session=session), symbol, limit)
