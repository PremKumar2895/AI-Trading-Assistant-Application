"""
Data router — picks a real-market provider by symbol/platform, else signals the
caller to fall back to vision (synthetic indices, unknown symbols, or no feed).

Returns (records, source_name) where records suit `ohlcv.from_provider_ohlcv`.
Forex/stock providers can be added here later behind the same interface.
"""
from .crypto_cdc import CryptoDotComProvider
from .yahoo import YahooProvider
from .twelvedata import TwelveDataProvider

MIN_BARS = 8


class DataRouter:
    def __init__(self):
        self._crypto = CryptoDotComProvider()
        self._yahoo = YahooProvider()
        self._twelve = TwelveDataProvider()   # used only if TWELVE_DATA_KEY is set

    def get(self, symbol, timeframe, platform=None, limit=300):
        s = str(symbol or "").upper()
        if not s or s == "UNKNOWN" or "IDX" in s:
            return None, None  # synthetic / unknown -> vision

        # 1) crypto exchange (best for real crypto pairs)
        recs = self._crypto.get_ohlcv(symbol, timeframe, limit=limit)
        if recs and len(recs) >= MIN_BARS:
            return recs, self._crypto.name

        # 2) Twelve Data for forex/stocks IF a key is configured (cleaner intraday)
        if self._twelve.enabled:
            recs = self._twelve.get_ohlcv(symbol, timeframe, limit=limit)
            if recs and len(recs) >= MIN_BARS:
                return recs, self._twelve.name

        # 3) Yahoo for forex / stocks (free, no key) — the default
        recs = self._yahoo.get_ohlcv(symbol, timeframe, limit=limit)
        if recs and len(recs) >= MIN_BARS:
            return recs, self._yahoo.name

        return None, None
