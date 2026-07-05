"""Fetches recent news headlines from the CryptoPanic developer API."""
import requests

POSTS_URL = "https://cryptopanic.com/api/developer/v2/posts/"

SYMBOL_TO_CURRENCY = {
    "BTCUSDT": "BTC",
    "ETHUSDT": "ETH",
}


def fetch_headlines(symbol, api_key, limit=10, session=None):
    currency = SYMBOL_TO_CURRENCY.get(symbol)
    if currency is None:
        return []
    session = session or requests.Session()
    response = session.get(
        POSTS_URL,
        params={"auth_token": api_key, "currencies": currency, "public": "true"},
        timeout=10,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
    titles = [post.get("title") for post in results]
    return [t for t in titles if t][:limit]
