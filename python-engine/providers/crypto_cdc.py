"""
Crypto.com Exchange public candlestick provider.

Free, no-auth REST endpoint. Returns normalised OHLCV records ready for
`ohlcv.from_provider_ohlcv`. TTL-cached so the per-frame loop never blocks on
repeated network calls. Uses stdlib urllib (no extra dependency).
"""
import json
import time
import urllib.request

BASE = "https://api.crypto.com/exchange/v1/public/get-candlestick"

# App timeframe -> Crypto.com timeframe. Sub-minute is unsupported -> nearest 1m.
_TF = {
    "5s": "1m", "15s": "1m", "30s": "1m",
    "1m": "1m", "3m": "5m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "12h": "12h",
    "1d": "1D", "1w": "7D",
}

_SYMBOL_ALIASES = {
    "BITCOIN": "BTC_USDT", "ETHEREUM": "ETH_USDT", "BTC": "BTC_USDT",
    "ETH": "ETH_USDT", "SOL": "SOL_USDT", "XRP": "XRP_USDT", "DOGE": "DOGE_USDT",
}

# Fiat currencies — a pair whose BASE is fiat is forex (e.g. EUR/USD), not crypto,
# so we must NOT route it to a crypto exchange (EUR_USDT would be the wrong market).
_FIAT = {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD", "CNY", "HKD", "SGD", "INR"}


class CryptoDotComProvider:
    name = "crypto.com"

    def __init__(self, ttl=4.0):
        self._cache = {}
        self._ttl = ttl

    def map_symbol(self, symbol):
        if not symbol:
            return None
        s = str(symbol).strip().upper()
        if s in _SYMBOL_ALIASES:
            return _SYMBOL_ALIASES[s]
        if "IDX" in s:                       # synthetic index -> no real market
            return None
        s = s.replace("-", "/").replace(" ", "")
        if "/" in s:
            base, quote = s.split("/", 1)
            if base in _FIAT:                # forex pair -> not crypto
                return None
            if quote in ("USD", "USDT", "USDC", "USDTUSD"):
                quote = "USDT"
            if base and quote:
                return f"{base}_{quote}"
        return None

    def map_timeframe(self, tf):
        return _TF.get(str(tf or "").lower())

    def get_ohlcv(self, symbol, timeframe, limit=50):
        inst = self.map_symbol(symbol)
        tfm = self.map_timeframe(timeframe)
        if not inst or not tfm:
            return None

        key = (inst, tfm)
        now = time.time()
        cached = self._cache.get(key)
        if cached and now - cached[0] < self._ttl:
            return cached[1]

        try:
            url = f"{BASE}?instrument_name={inst}&timeframe={tfm}&count={limit}"
            with urllib.request.urlopen(url, timeout=4) as resp:
                payload = json.load(resp)
            rows = (payload.get("result") or {}).get("data") or []
            recs = [
                {
                    "open": float(r["o"]), "high": float(r["h"]),
                    "low": float(r["l"]), "close": float(r["c"]),
                    "volume": float(r.get("v", 0.0)),
                    "t": int(r["t"]) // 1000 if r.get("t") else None,  # ms -> s
                }
                for r in rows
            ]
            recs = recs[-limit:]
            self._cache[key] = (now, recs)
            return recs
        except Exception as e:
            print(f"crypto.com fetch error ({inst} {tfm}): {e}")
            return None
