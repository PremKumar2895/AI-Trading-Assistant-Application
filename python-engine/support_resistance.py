"""
Support / resistance detection via fractal pivots.

A pivot high is a bar whose high is the local max over +/-`width` bars (a swing the
market rejected — "emotion" turning point); a pivot low is the mirror. Nearby pivots
are clustered into levels. Used both for live display and as model features
(distance-to-level normalised by ATR = "how close are we to a decision zone").
"""
import numpy as np


def pivots(high, low, width=3):
    """Return (resistance_prices, support_prices) from confirmed fractal pivots."""
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    n = len(h)
    res, sup = [], []
    for i in range(width, n - width):
        win_h = h[i - width:i + width + 1]
        win_l = l[i - width:i + width + 1]
        if h[i] == win_h.max():
            res.append(h[i])
        if l[i] == win_l.min():
            sup.append(l[i])
    return res, sup


def cluster_levels(prices, tol):
    """Merge levels within `tol` into averaged levels (strongest first by count)."""
    if not prices:
        return []
    prices = sorted(prices)
    clusters = [[prices[0]]]
    for p in prices[1:]:
        if abs(p - clusters[-1][-1]) <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = [(float(np.mean(c)), len(c)) for c in clusters]
    levels.sort(key=lambda x: x[1], reverse=True)
    return levels


def nearest_levels(df, atr_val, width=3):
    """Nearest support below and resistance above the latest close."""
    if df is None or len(df) < (2 * width + 2):
        return {"support": None, "resistance": None}
    res, sup = pivots(df["high"], df["low"], width)
    close = float(df["close"].iloc[-1])
    tol = max(atr_val * 0.5, close * 1e-4) if atr_val else close * 1e-3

    res_levels = [lv for lv, _ in cluster_levels(res, tol) if lv > close]
    sup_levels = [lv for lv, _ in cluster_levels(sup, tol) if lv < close]
    return {
        "support": max(sup_levels) if sup_levels else None,
        "resistance": min(res_levels) if res_levels else None,
    }
