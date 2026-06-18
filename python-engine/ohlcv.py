"""
OHLCV construction.

The vision layer returns a list of detected candles ordered left -> right
(oldest -> newest) — this *is* the price history visible on the chart. We turn it
into a normalised OHLCV DataFrame so the full indicator stack can run on it.

Pixel-y is inverted (smaller y = higher price), so price proxy = -y. Indicators
depend on *relative* movement, so this monotonic proxy is directionally valid even
without a calibrated price-per-pixel map. If a real OHLCV feed (crypto/forex/stocks
API) is wired in later, it can produce the same DataFrame and bypass this module.
"""
import pandas as pd
import numpy as np

COLUMNS = ["open", "high", "low", "close", "volume"]


def candles_to_ohlcv(candles, price_map=None, y_offset=0):
    """Convert vision candles (left->right) into an OHLCV DataFrame.

    If `price_map` is given (callable: full-image pixel-y -> real price, from
    `calibrate.build_price_map`), candle pixels are mapped to *real* prices and
    `y_offset` shifts crop-relative y into full-image coordinates. Otherwise the
    inverted-pixel proxy (-y) is used.

    Prices are shifted to be strictly positive so ratio-based indicators (MFI,
    etc.) behave. Constant shift/scale does not affect diffs, crossovers,
    %-based oscillators or band relationships.
    """
    if not candles:
        return pd.DataFrame(columns=COLUMNS)

    rows = []
    for c in candles:
        y = float(c.get("y", 0.0))
        h = float(c.get("total_height", 1.0)) or 1.0

        if price_map is not None:
            p_top = price_map(y_offset + y)            # top of candle
            p_bot = price_map(y_offset + y + h)        # bottom of candle
            top, bottom = max(p_top, p_bot), min(p_top, p_bot)
        else:
            top = -y                 # higher price (top of candle)
            bottom = -(y + h)        # lower price (bottom of candle)

        if c.get("type") == "bullish":
            o, cl = bottom, top
        else:                    # bearish (or unknown -> treat as down)
            o, cl = top, bottom

        strength = float(c.get("strength", 0.5))
        width = float(c.get("body_width", 3.0)) or 3.0
        vol = max(1.0, strength * h * width)
        rows.append((o, top, bottom, cl, vol))

    df = pd.DataFrame(rows, columns=COLUMNS)

    price_cols = ["open", "high", "low", "close"]
    gmin = float(df[price_cols].min().min())
    shift = 1.0 - gmin if gmin <= 0 else 0.0
    if shift:
        df[price_cols] = df[price_cols] + shift

    return df


def from_provider_ohlcv(records):
    """Build the same DataFrame from a real-data provider.

    `records`: iterable of dict/tuple with open/high/low/close[/volume].
    Kept so API providers (crypto/forex/stocks) feed the identical pipeline.
    """
    if not records:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(records)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = 1.0 if col == "volume" else np.nan
    return df[COLUMNS].astype(float).reset_index(drop=True)
