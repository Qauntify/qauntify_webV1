import pytest

from signals.news_client import (
    FEED_URLS,
    fetch_feed_titles,
    fetch_headlines,
    filter_headlines,
)

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


def test_fetch_feed_titles_collects_all_feeds_once():
    session = FakeSession({
        FEED_URLS[0]: _rss("Bitcoin breaks resistance", "Solana hits new high"),
        FEED_URLS[1]: _rss("Ether steadies after selloff"),
    })
    titles = fetch_feed_titles(session=session)
    assert "Bitcoin breaks resistance" in titles
    assert "Solana hits new high" in titles
    assert "Ether steadies after selloff" in titles
    assert session.requested == list(FEED_URLS)


def test_fetch_feed_titles_raises_when_all_feeds_fail():
    session = FakeSession({url: ConnectionError("down") for url in FEED_URLS})
    with pytest.raises(RuntimeError, match="all RSS feeds unavailable"):
        fetch_feed_titles(session=session)


def test_filter_headlines_matches_dedupes_and_limits_without_network():
    titles = (["Bitcoin breaks resistance", "Solana hits new high",
               "Bitcoin breaks resistance"]
              + [f"Bitcoin headline number {i}" for i in range(15)])
    headlines = filter_headlines(titles, "BTCUSDT")
    assert len(headlines) == 10
    assert headlines.count("Bitcoin breaks resistance") == 1
    assert "Solana hits new high" not in headlines
    assert filter_headlines(titles, "DOGEUSDT") == []


def test_gold_and_forex_feeds_are_polled():
    # The feed list must include at least one non-crypto source so PAXG/GBP
    # confirmation isn't permanently running on empty headlines.
    non_crypto = [u for u in FEED_URLS
                  if "fxstreet" in u or "forexlive" in u]
    assert non_crypto, f"no gold/forex feed in {FEED_URLS}"


def test_gold_headlines_match_xau_and_gold():
    titles = [
        "Gold retreats from record high on dollar strength",
        "XAU/USD holds above key support",
        "Bitcoin ETF inflows surge",
    ]
    headlines = filter_headlines(titles, "PAXGUSDT")
    assert "Gold retreats from record high on dollar strength" in headlines
    assert "XAU/USD holds above key support" in headlines
    assert "Bitcoin ETF inflows surge" not in headlines


def test_gbp_headlines_match_boe_and_sterling():
    titles = [
        "GBP/USD climbs as BoE holds rates",
        "Sterling rallies on inflation surprise",
        "Ethereum upgrade ships",
    ]
    headlines = filter_headlines(titles, "GBPUSDT")
    assert "GBP/USD climbs as BoE holds rates" in headlines
    assert "Sterling rallies on inflation surprise" in headlines
    assert "Ethereum upgrade ships" not in headlines
