"""
Chart payload builder for the in-overlay annotated prediction chart.

Produces a compact, JSON-serialisable snapshot of the most recent candles plus the
overlays a trader wants to see: EMA(9/21/50), the nearest support/resistance, and a
forward *projection* of likely movement derived from the signal direction and ATR.

The projection is an illustrative path (direction × ATR), NOT a guarantee — the UI
labels it as such. Kept to ~40 candles so it streams cheaply over the local socket.
"""
import numpy as np

import indicators as ta


def _f(x, nd=5):
    try:
        v = float(x)
        return round(v, nd) if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def build_chart_payload(df, levels=None, signal="WAIT", trend="NEUTRAL",
                        n=40, horizon=6):
    if df is None or len(df) < 5:
        return None

    close_full = df["close"]
    ema9 = ta.ema(close_full, 9)
    ema21 = ta.ema(close_full, 21)
    ema50 = ta.ema(close_full, 50)
    atr = _f(ta.atr(df["high"], df["low"], close_full, 14).iloc[-1]) or 0.0

    d = df.tail(n)
    candles = [
        {"o": _f(o), "h": _f(h), "l": _f(l), "c": _f(c)}
        for o, h, l, c in zip(d["open"], d["high"], d["low"], d["close"])
    ]

    def tail_list(series):
        return [_f(x) for x in series.tail(n)]

    last_close = _f(close_full.iloc[-1])

    # Forward projection: a sloped path in the signal's direction, scaled by ATR.
    projection = None
    if signal in ("BUY", "SELL") and atr > 0 and last_close is not None:
        sign = 1 if signal == "BUY" else -1
        step = atr * 0.55
        projection = [_f(last_close + sign * step * (i + 1)) for i in range(horizon)]

    sup = _f(levels.get("support")) if levels else None
    res = _f(levels.get("resistance")) if levels else None

    return {
        "candles": candles,
        "ema9": tail_list(ema9),
        "ema21": tail_list(ema21),
        "ema50": tail_list(ema50),
        "support": sup,
        "resistance": res,
        "projection": projection,
        "signal": signal,
        "trend": trend,
        "atr": _f(atr),
        "last_close": last_close,
    }
