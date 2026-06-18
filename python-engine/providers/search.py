"""
Symbol search — type-ahead asset lookup for the picker.

Uses Yahoo Finance's free search endpoint (no API key) to resolve a free-text
query into tradable symbols across forex, stocks, ETFs, crypto, indices and
commodities. Returns app-canonical symbols the analysis engine can fetch.
"""
import json
import time
import urllib.parse
import urllib.request

SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

# Yahoo quoteType -> friendly asset class label.
_TYPE = {
    "CURRENCY": "FX",
    "CRYPTOCURRENCY": "Crypto",
    "EQUITY": "Stock",
    "ETF": "ETF",
    "INDEX": "Index",
    "FUTURE": "Commodity",
    "MUTUALFUND": "Fund",
}

# A few always-available favourites so the picker is useful even before typing.
POPULAR = [
    {"symbol": "EUR/USD", "yahoo": "EURUSD=X", "name": "Euro / US Dollar", "type": "FX"},
    {"symbol": "GBP/USD", "yahoo": "GBPUSD=X", "name": "British Pound / US Dollar", "type": "FX"},
    {"symbol": "USD/JPY", "yahoo": "USDJPY=X", "name": "US Dollar / Japanese Yen", "type": "FX"},
    {"symbol": "CAD/JPY", "yahoo": "CADJPY=X", "name": "Canadian Dollar / Japanese Yen", "type": "FX"},
    {"symbol": "AUD/USD", "yahoo": "AUDUSD=X", "name": "Australian Dollar / US Dollar", "type": "FX"},
    {"symbol": "BTC/USD", "yahoo": "BTC-USD", "name": "Bitcoin / US Dollar", "type": "Crypto"},
    {"symbol": "ETH/USD", "yahoo": "ETH-USD", "name": "Ethereum / US Dollar", "type": "Crypto"},
    {"symbol": "AAPL", "yahoo": "AAPL", "name": "Apple Inc.", "type": "Stock"},
    {"symbol": "TSLA", "yahoo": "TSLA", "name": "Tesla Inc.", "type": "Stock"},
    {"symbol": "GC=F", "yahoo": "GC=F", "name": "Gold (Futures)", "type": "Commodity"},
]

_cache = {}
_TTL = 60.0


def _canonical(sym, qtype):
    """Yahoo symbol -> app-canonical symbol the router/analyze understands."""
    s = str(sym or "").upper()
    if qtype == "CURRENCY" and s.endswith("=X") and len(s) == 8:
        return f"{s[0:3]}/{s[3:6]}"               # EURUSD=X -> EUR/USD
    if qtype == "CRYPTOCURRENCY" and s.endswith("-USD"):
        return f"{s[:-4]}/USD"                     # BTC-USD -> BTC/USD
    return sym                                     # equities, indices (^), futures (=F)


def search(query, limit=12):
    """Return up to `limit` matching assets for a free-text query."""
    q = (query or "").strip()
    if not q:
        return POPULAR[:limit]

    key = q.lower()
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < _TTL:
        return cached[1]

    try:
        params = urllib.parse.urlencode(
            {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}
        )
        req = urllib.request.Request(f"{SEARCH_URL}?{params}", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.load(resp)
        out = []
        for it in payload.get("quotes", []):
            sym = it.get("symbol")
            qtype = it.get("quoteType")
            if not sym or qtype not in _TYPE:
                continue
            name = it.get("shortname") or it.get("longname") or sym
            out.append(
                {
                    "symbol": _canonical(sym, qtype),
                    "yahoo": sym,
                    "name": name,
                    "type": _TYPE[qtype],
                    "exchange": it.get("exchange", ""),
                }
            )
            if len(out) >= limit:
                break
        if out:
            _cache[key] = (now, out)
        return out
    except Exception as e:
        print(f"search error ({q}): {e}")
        # graceful fallback: filter the popular list
        ql = q.lower()
        return [p for p in POPULAR if ql in p["symbol"].lower() or ql in p["name"].lower()]
