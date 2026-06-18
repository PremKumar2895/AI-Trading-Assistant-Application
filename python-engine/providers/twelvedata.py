"""
Twelve Data provider (optional) — cleaner intraday history for forex/stocks.

Activates ONLY when the TWELVE_DATA_KEY environment variable is set; otherwise the
router skips it and uses Yahoo (free, no key). Free tier allows ~8 requests/min, so
this is best for the backtester and occasional analysis, not high-frequency polling.
"""
import json
import os
import time
import urllib.parse
import urllib.request

BASE = "https://api.twelvedata.com/time_series"

_TF = {
    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1day", "1w": "1week",
}


class TwelveDataProvider:
    name = "twelvedata"

    def __init__(self, ttl=5.0):
        self._cache = {}
        self._ttl = ttl
        self._key = os.environ.get("TWELVE_DATA_KEY", "").strip()

    @property
    def enabled(self):
        return bool(self._key)

    def map_symbol(self, symbol):
        if not symbol:
            return None
        s = str(symbol).strip().upper()
        if "IDX" in s:
            return None
        if "=" in s or s.startswith("^"):
            return None                       # Yahoo-specific format — let Yahoo handle
        if "/" in s:
            return s                          # EUR/USD, BTC/USD accepted as-is
        if s.isalpha() and 2 <= len(s) <= 6:
            return s                          # equity ticker
        return None

    def get_ohlcv(self, symbol, timeframe, limit=300):
        if not self._key:
            return None
        sym = self.map_symbol(symbol)
        interval = _TF.get(str(timeframe or "").lower())
        if not sym or not interval:
            return None
        key = (sym, interval)
        now = time.time()
        c = self._cache.get(key)
        if c and now - c[0] < self._ttl:
            return c[1]
        try:
            params = urllib.parse.urlencode(
                {"symbol": sym, "interval": interval, "outputsize": min(limit, 5000),
                 "apikey": self._key, "order": "ASC"}
            )
            with urllib.request.urlopen(f"{BASE}?{params}", timeout=8) as r:
                d = json.load(r)
            if d.get("status") == "error" or "values" not in d:
                return None
            recs = []
            for v in d["values"]:
                recs.append({
                    "open": float(v["open"]), "high": float(v["high"]),
                    "low": float(v["low"]), "close": float(v["close"]),
                    "volume": float(v.get("volume") or 0.0),
                    "t": int(time.mktime(time.strptime(v["datetime"][:19],
                          "%Y-%m-%d %H:%M:%S"))) if " " in v["datetime"] else None,
                })
            recs = recs[-limit:]
            self._cache[key] = (now, recs)
            return recs
        except Exception as e:
            print(f"twelvedata error ({sym} {interval}): {e}")
            return None
