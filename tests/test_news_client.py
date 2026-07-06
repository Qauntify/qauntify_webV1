import pytest

from signals.news_client import FEED_URLS, fetch_headlines

RSS_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
{items}
</channel></rss>"""


def _rss(*titles):
    items = "\n".join(f"<item><title>{t}</title></item>" for t in titles)
    return RSS_TEMPLATE.format(items=items).encode()


ATOM_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>Ethereum upgrade ships on mainnet</title></entry>
</feed>"""


class FakeResponse:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Maps feed URL -> bytes payload, Exception, or error status int."""

    def __init__(self, responses):
        self._responses = responses
        self.requested = []

    def get(self, url, timeout=None):
        self.requested.append(url)
        result = self._responses.get(url, b"<rss><channel></channel></rss>")
        if isinstance(result, Exception):
            raise result
        if isinstance(result, int):
            return FakeResponse(b"", status=result)
        return FakeResponse(result)


def test_fetch_headlines_filters_by_symbol_keywords():
    session = FakeSession({
        FEED_URLS[0]: _rss(
            "Bitcoin breaks resistance at 108K",
            "Solana hits new high",
            "BTC ETF inflows surge",
        ),
    })
    headlines = fetch_headlines("BTCUSDT", session=session)
    assert headlines == [
        "Bitcoin breaks resistance at 108K",
        "BTC ETF inflows surge",
    ]
    assert session.requested == list(FEED_URLS)


def test_fetch_headlines_uses_word_boundaries():
    session = FakeSession({
        FEED_URLS[0]: _rss(
            "Markets move together this week",  # "eth" inside a word: no match
            "Ether steadies after selloff",
        ),
    })
    assert fetch_headlines("ETHUSDT", session=session) == [
        "Ether steadies after selloff",
    ]


def test_fetch_headlines_parses_atom_feeds():
    session = FakeSession({FEED_URLS[1]: ATOM_FEED})
    assert fetch_headlines("ETHUSDT", session=session) == [
        "Ethereum upgrade ships on mainnet",
    ]


def test_fetch_headlines_dedupes_across_feeds_and_respects_limit():
    story = "Bitcoin breaks resistance at 108K"
    many = [f"Bitcoin headline number {i}" for i in range(15)]
    session = FakeSession({
        FEED_URLS[0]: _rss(story, *many),
        FEED_URLS[1]: _rss(story),  # duplicate story from a second outlet
    })
    headlines = fetch_headlines("BTCUSDT", session=session)
    assert len(headlines) == 10
    assert headlines.count(story) == 1


def test_fetch_headlines_survives_one_broken_feed():
    session = FakeSession({
        FEED_URLS[0]: ConnectionError("feed down"),
        FEED_URLS[1]: 500,
        FEED_URLS[2]: _rss("Bitcoin steadies above support"),
    })
    assert fetch_headlines("BTCUSDT", session=session) == [
        "Bitcoin steadies above support",
    ]


def test_fetch_headlines_raises_when_all_feeds_fail():
    session = FakeSession({url: ConnectionError("down") for url in FEED_URLS})
    with pytest.raises(RuntimeError, match="all RSS feeds unavailable"):
        fetch_headlines("BTCUSDT", session=session)


def test_fetch_headlines_unknown_symbol_returns_empty_without_network():
    session = FakeSession({})
    assert fetch_headlines("DOGEUSDT", session=session) == []
    assert session.requested == []
