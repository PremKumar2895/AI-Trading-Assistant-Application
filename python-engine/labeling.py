"""
Self-supervised labelling.

Two targets:
  • make_labels        — simple "higher after `horizon` bars?" (the raw binary bet).
  • make_barrier_labels — triple-barrier-lite: within `horizon` bars, does price hit
    +k·ATR (win) before −k·ATR (loss)? This is a more *learnable* target — it rewards
    a real directional move of meaningful size, not single-bar noise — so the model
    has a better chance of finding signal (ML v2).
"""
import numpy as np


def make_labels(df, horizon=1, deadband=0.0):
    """Return a Series: 1 if up after `horizon` bars, 0 if down, NaN if flat/edge."""
    close = df["close"]
    future = close.shift(-horizon)
    ret = (future - close) / close
    label = np.where(ret > deadband, 1.0, np.where(ret < -deadband, 0.0, np.nan))
    out = close.copy().astype(float)
    out[:] = label
    return out


def make_barrier_labels(df, horizon=6, k=0.5):
    """Triple-barrier-lite. 1 if +k·ATR hit before −k·ATR within horizon; 0 if the
    down barrier first; NaN if neither (no decisive move) or at the right edge."""
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    n = len(close)
    # ATR proxy (rolling true range mean) for the barrier width
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(np.abs(high[1:] - close[:-1]),
                               np.abs(low[1:] - close[:-1])))
    atr = np.full(n, np.nan)
    win = 14
    for i in range(win, n):
        atr[i] = tr[i - win:i].mean()
    labels = np.full(n, np.nan)
    for i in range(win, n - horizon):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        up, dn = close[i] + k * a, close[i] - k * a
        lab = np.nan
        for j in range(i + 1, i + 1 + horizon):
            if high[j] >= up:
                lab = 1.0
                break
            if low[j] <= dn:
                lab = 0.0
                break
        labels[i] = lab
    out = df["close"].copy().astype(float)
    out[:] = labels
    return out
