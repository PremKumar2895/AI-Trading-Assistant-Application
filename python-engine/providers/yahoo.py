"""
Yahoo Finance provider — forex and stocks (and crypto as a fallback).

Free, no-auth chart endpoint returning intraday OHLCV. Used for instruments the
crypto exchange can't serve: FX pairs (EURUSD=X) and equities (AAPL). Forex has no
centralised volume, so `volume` is 0 there — volume indicators degrade gracefully.
Trailing null bars (common near the live edge) are filtered out.
"""
import json
import time
import urllib.request

BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"
_HEADERS = {"User-Agent": "Mozilla/5.0"}

_FIAT = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY", "HKD", "SGD", "INR"}

# App timeframe -> (yahoo interval, range). Ranges chosen for ~200+ bars per TF.
_TF = {
    "5s": ("1m", "5d"), "15s": ("1m", "5d"), "30s": ("1m", "5d"),
    "1m": ("1m", "5d"), "2m": ("2m", "5d"), "3m": ("5m", "1mo"),
    "5m": ("5m", "1mo"), "15m": ("15m", "1mo"), "30m": ("30m", "1mo"),
    "1h": ("60m", "3mo"), "2h": ("60m", "3mo"), "4h": ("60m", "3mo"),
    "1d": ("1d", "1y"), "1w": ("1wk", "2y"),
}


class YahooProvider:
    name = "yahoo"

    def __init__(self, ttl=5.0):
        self._cache = {}
        self._ttl = ttl

    def map_symbol(self, symbol):
        if not symbol:
            return None
        s = str(symbol).strip().upper()
        if not s or "IDX" in s:
            return None
        # Already a raw Yahoo symbol (forex =X, future =F, index ^GSPC) -> pass through.
        if "=" in s or s.startswith("^"):
            return s
        if "/" in s:
            base, quote = s.split("/", 1)
            quote = quote.replace("USDT", "USD").replace("USDC", "USD")
            if base in _FIAT:
                return f"{base}{quote}=X"        # forex
            return f"{base}-{quote}"             # crypto fallback (BTC-USD)
        if "-" in s and s.endswith("USD"):
            return s                              # BTC-USD style (pass through)
        if s.isalpha() and 2 <= len(s) <= 6:
            return s                              # equity ticker
        return None

    def map_timeframe(self, tf):
        return _TF.get(str(tf or "").lower())

    def get_ohlcv(self, symbol, timeframe, limit=300):
        ysym = self.map_symbol(symbol)
        tfm = self.map_timeframe(timeframe)
        if not ysym or not tfm:
            return None
        interval, rng = tfm

        key = (ysym, interval, rng)
        now = time.time()
        cached = self._cache.get(key)
        if cached and now - cached[0] < self._ttl:
            return cached[1]

        try:
            url = f"{BASE}{ysym}?interval={interval}&range={rng}"
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=6) as resp:
                payload = json.load(resp)
            res = (payload.get("chart") or {}).get("result")
            if not res:
                return None
            q = res[0]["indicators"]["quote"][0]
            o, h, l, c = q.get("open"), q.get("high"), q.get("low"), q.get("close")
            v = q.get("volume") or []
            tstamps = res[0].get("timestamp") or []
            recs = []
            for i in range(len(c or [])):
                if c[i] is None or o[i] is None or h[i] is None or l[i] is None:
                    continue  # skip Yahoo's null gaps / trailing bar
                recs.append(
                    {
                        "open": float(o[i]), "high": float(h[i]),
                        "low": float(l[i]), "close": float(c[i]),
                        "volume": float(v[i]) if i < len(v) and v[i] else 0.0,
                        "t": int(tstamps[i]) if i < len(tstamps) else None,
                    }
                )
            recs = recs[-limit:]
            self._cache[key] = (now, recs)
            return recs
        except Exception as e:
            print(f"yahoo fetch error ({ysym} {interval}): {e}")
            return None
