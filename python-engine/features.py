"""
Feature engineering for the self-learning model.

Turns OHLCV into a causal (past-only, no look-ahead) numeric feature vector that
encodes the things a discretionary trader reads:

  * trend       — EMA stack distances, EMA slope, ADX/DI, MACD
  * momentum    — RSI, Stochastic, CCI, Williams %R, ROC, MFI
  * volatility  — ATR/price regime, Bollinger %B & bandwidth
  * psychology  — candle body fraction, upper/lower wick (rejection = fear/greed),
                  direction streak (herd behaviour)
  * structure   — position within recent range, distance to support/resistance (ATR units)

`FEATURE_NAMES` is the single source of truth for column order so training and
inference always agree.
"""
import numpy as np
import pandas as pd

import indicators as ta

FEATURE_NAMES = [
    "ret1", "ret3", "ret5",
    "ema9_dist", "ema21_dist", "ema50_dist", "ema9_slope", "ema_stack",
    "macd_hist", "adx", "di_diff",
    "rsi", "stoch_k", "cci", "williams_r", "roc", "mfi",
    "atr_pct", "bb_pb", "bb_width",
    "body_frac", "upper_wick", "lower_wick", "dir_streak",
    "range_pos", "dist_res_atr", "dist_sup_atr",
    "obv_slope",
]


def build_features(df):
    """Return a DataFrame of causal features aligned to `df` (NaNs early)."""
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    eps = 1e-9

    ema9, ema21, ema50 = ta.ema(c, 9), ta.ema(c, 21), ta.ema(c, 50)
    atr = ta.atr(h, l, c, 14).replace(0, np.nan)
    macd_line, macd_sig, macd_hist = ta.macd(c)
    adx, plus_di, minus_di = ta.adx(h, l, c)
    stoch_k, _ = ta.stochastic(h, l, c)
    bb_u, bb_m, bb_l, bb_w, bb_pb = ta.bollinger(c)
    obv = ta.obv(c, v)

    f = pd.DataFrame(index=df.index)
    f["ret1"] = c.pct_change(1)
    f["ret3"] = c.pct_change(3)
    f["ret5"] = c.pct_change(5)
    f["ema9_dist"] = (c - ema9) / atr
    f["ema21_dist"] = (c - ema21) / atr
    f["ema50_dist"] = (c - ema50) / atr
    f["ema9_slope"] = ema9.diff() / atr
    f["ema_stack"] = np.sign(ema9 - ema21) + np.sign(ema21 - ema50)
    f["macd_hist"] = macd_hist / atr
    f["adx"] = adx
    f["di_diff"] = plus_di - minus_di
    f["rsi"] = ta.rsi(c)
    f["stoch_k"] = stoch_k
    f["cci"] = ta.cci(h, l, c)
    f["williams_r"] = ta.williams_r(h, l, c)
    f["roc"] = ta.roc(c)
    f["mfi"] = ta.mfi(h, l, c, v)
    f["atr_pct"] = atr / c
    f["bb_pb"] = bb_pb
    f["bb_width"] = bb_w

    # ---- candle psychology ----
    body = (c - o)
    rng = (h - l).replace(0, np.nan)
    f["body_frac"] = body.abs() / rng
    upper = h - c.where(c >= o, o)
    lower = o.where(o <= c, c) - l
    f["upper_wick"] = upper / rng
    f["lower_wick"] = lower / rng

    direction = np.sign(body)
    streak = direction.copy()
    vals = direction.fillna(0).values
    out = np.zeros(len(vals))
    run = 0
    for i in range(len(vals)):
        if i > 0 and vals[i] == vals[i - 1] and vals[i] != 0:
            run += vals[i]
        else:
            run = vals[i]
        out[i] = run
    f["dir_streak"] = out

    # ---- structure / support-resistance (rolling, causal) ----
    win = 20
    roll_hi = h.rolling(win, min_periods=5).max()
    roll_lo = l.rolling(win, min_periods=5).min()
    span = (roll_hi - roll_lo).replace(0, np.nan)
    f["range_pos"] = (c - roll_lo) / span
    f["dist_res_atr"] = (roll_hi - c) / atr
    f["dist_sup_atr"] = (c - roll_lo) / atr

    f["obv_slope"] = (obv - obv.shift(3)) / (v.rolling(3, min_periods=1).mean() + eps)

    f = f.reindex(columns=FEATURE_NAMES)
    return f.replace([np.inf, -np.inf], np.nan)


def latest_row(df):
    """Feature vector (1 x F numpy) for the most recent bar, or None if not ready."""
    if df is None or len(df) < 30:
        return None
    f = build_features(df).iloc[[-1]]
    if f.isna().any(axis=None):
        f = f.fillna(0.0)
    return f.values
