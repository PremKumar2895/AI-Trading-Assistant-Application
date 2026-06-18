"""
Comprehensive technical-indicator library (pure pandas/numpy).

Implements trend, momentum, volatility, volume and candlestick-pattern indicators
so the decision engine can build multi-factor confluence. No TA-Lib / pandas-ta
dependency (avoids compiled-wheel pain on Windows); all maths is self-contained.

Every function takes/returns pandas Series aligned to the input OHLCV DataFrame.
`compute_all(df)` returns a flat dict of latest scalar values + helper series the
decision engine votes on.
"""
import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def _wilder(series, n):
    """Wilder's smoothing (used by RSI/ATR/ADX)."""
    return series.ewm(alpha=1.0 / n, adjust=False).mean()


def _last(series, default=np.nan):
    try:
        v = float(series.iloc[-1])
        return v if np.isfinite(v) else default
    except (IndexError, ValueError, TypeError):
        return default


# ----------------------------------------------------------------------------
# moving averages / trend
# ----------------------------------------------------------------------------
def sma(close, n):
    return close.rolling(n, min_periods=1).mean()


def ema(close, n):
    return close.ewm(span=n, adjust=False, min_periods=1).mean()


def wma(close, n):
    weights = np.arange(1, n + 1)
    return close.rolling(n).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def macd(close, fast=12, slow=26, signal=9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def true_range(high, low, close):
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr


def atr(high, low, close, n=14):
    return _wilder(true_range(high, low, close), n)


def adx(high, low, close, n=14):
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = true_range(high, low, close)
    atr_n = _wilder(tr, n).replace(0, np.nan)
    plus_di = 100 * _wilder(plus_dm, n) / atr_n
    minus_di = 100 * _wilder(minus_dm, n) / atr_n
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    adx_line = _wilder(dx.fillna(0), n)
    return adx_line, plus_di, minus_di


def supertrend(high, low, close, period=10, mult=3.0):
    # Operate on numpy arrays — the band recursion is sequential, but numpy indexing
    # is ~20-50x faster than pandas .iat (matters when called per-bar in the backtest).
    atr_n = atr(high, low, close, period).to_numpy()
    c = close.to_numpy()
    hl2 = ((high + low) / 2.0).to_numpy()
    upper = hl2 + mult * atr_n
    lower = hl2 - mult * atr_n
    fu = upper.copy()
    fl = lower.copy()
    direction = np.ones(len(c), dtype=float)
    for i in range(1, len(c)):
        fu[i] = min(upper[i], fu[i - 1]) if c[i - 1] <= fu[i - 1] else upper[i]
        fl[i] = max(lower[i], fl[i - 1]) if c[i - 1] >= fl[i - 1] else lower[i]
        if c[i] > fu[i - 1]:
            direction[i] = 1
        elif c[i] < fl[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
    return pd.Series(direction, index=close.index)


def parabolic_sar(high, low, step=0.02, max_step=0.2):
    h = high.to_numpy()
    l = low.to_numpy()
    length = len(h)
    psar = l.astype(float).copy()
    bull = True
    af = step
    ep = h[0]
    psar[0] = l[0]
    for i in range(1, length):
        psar[i] = psar[i - 1] + af * (ep - psar[i - 1])
        if bull:
            if l[i] < psar[i]:
                bull = False
                psar[i] = ep
                ep = l[i]
                af = step
            elif h[i] > ep:
                ep = h[i]
                af = min(af + step, max_step)
        else:
            if h[i] > psar[i]:
                bull = True
                psar[i] = ep
                ep = h[i]
                af = step
            elif l[i] < ep:
                ep = l[i]
                af = min(af + step, max_step)
    return pd.Series(psar, index=high.index)


def ichimoku(high, low, close):
    tenkan = (high.rolling(9, min_periods=1).max() + low.rolling(9, min_periods=1).min()) / 2
    kijun = (high.rolling(26, min_periods=1).max() + low.rolling(26, min_periods=1).min()) / 2
    senkou_a = ((tenkan + kijun) / 2)
    senkou_b = (high.rolling(52, min_periods=1).max() + low.rolling(52, min_periods=1).min()) / 2
    return tenkan, kijun, senkou_a, senkou_b


# ----------------------------------------------------------------------------
# momentum / oscillators
# ----------------------------------------------------------------------------
def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder(gain, n)
    avg_loss = _wilder(loss, n)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.mask(avg_loss == 0, 100.0)          # only gains -> 100
    out = out.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return out.fillna(50)


def stochastic(high, low, close, k=14, d=3):
    ll = low.rolling(k, min_periods=1).min()
    hh = high.rolling(k, min_periods=1).max()
    rng = (hh - ll).replace(0, np.nan)
    percent_k = (100 * (close - ll) / rng).fillna(50)
    percent_d = percent_k.rolling(d, min_periods=1).mean()
    return percent_k, percent_d


def stoch_rsi(close, n=14, k=3, d=3):
    r = rsi(close, n)
    ll = r.rolling(n, min_periods=1).min()
    hh = r.rolling(n, min_periods=1).max()
    rng = (hh - ll).replace(0, np.nan)
    sr = ((r - ll) / rng).fillna(0.5)
    return (sr.rolling(k, min_periods=1).mean() * 100)


def cci(high, low, close, n=20):
    tp = (high + low + close) / 3
    ma = tp.rolling(n, min_periods=1).mean()
    md = (tp - ma).abs().rolling(n, min_periods=1).mean().replace(0, np.nan)
    return ((tp - ma) / (0.015 * md)).fillna(0)


def williams_r(high, low, close, n=14):
    hh = high.rolling(n, min_periods=1).max()
    ll = low.rolling(n, min_periods=1).min()
    rng = (hh - ll).replace(0, np.nan)
    return (-100 * (hh - close) / rng).fillna(-50)


def roc(close, n=9):
    return close.pct_change(n).fillna(0) * 100


def mfi(high, low, close, volume, n=14):
    tp = (high + low + close) / 3
    rmf = tp * volume
    pos = rmf.where(tp > tp.shift(1), 0.0)
    neg = rmf.where(tp < tp.shift(1), 0.0)
    pos_sum = pos.rolling(n, min_periods=1).sum()
    neg_sum = neg.rolling(n, min_periods=1).sum().replace(0, np.nan)
    mr = pos_sum / neg_sum
    return (100 - 100 / (1 + mr)).fillna(50)


# ----------------------------------------------------------------------------
# volatility / channels
# ----------------------------------------------------------------------------
def bollinger(close, n=20, mult=2.0):
    mid = close.rolling(n, min_periods=1).mean()
    std = close.rolling(n, min_periods=1).std(ddof=0).fillna(0)
    upper = mid + mult * std
    lower = mid - mult * std
    width = (upper - lower) / mid.replace(0, np.nan)
    rng = (upper - lower).replace(0, np.nan)
    percent_b = ((close - lower) / rng).fillna(0.5)
    return upper, mid, lower, width.fillna(0), percent_b


def keltner(high, low, close, n=20, mult=2.0):
    mid = ema(close, n)
    rng = atr(high, low, close, n)
    return mid + mult * rng, mid, mid - mult * rng


def donchian(high, low, n=20):
    upper = high.rolling(n, min_periods=1).max()
    lower = low.rolling(n, min_periods=1).min()
    return upper, (upper + lower) / 2, lower


# ----------------------------------------------------------------------------
# volume
# ----------------------------------------------------------------------------
def obv(close, volume):
    sign = np.sign(close.diff().fillna(0))
    return (sign * volume).cumsum()


def vwap(high, low, close, volume):
    tp = (high + low + close) / 3
    cum_vol = volume.cumsum().replace(0, np.nan)
    return (tp * volume).cumsum() / cum_vol


# ----------------------------------------------------------------------------
# candlestick patterns (return label of last bar, or "")
# ----------------------------------------------------------------------------
def detect_pattern(df):
    if len(df) < 2:
        return ""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper_wick = h - c.where(c >= o, o)
    lower_wick = o.where(o <= c, c) - l
    avg_body = body.rolling(10, min_periods=1).mean()

    i = -1
    b = body.iloc[i]
    r = rng.iloc[i] if np.isfinite(rng.iloc[i]) else b + 1e-9
    uw, lw = upper_wick.iloc[i], lower_wick.iloc[i]
    bull = c.iloc[i] > o.iloc[i]

    # Doji
    if b <= 0.1 * r:
        return "doji"
    # Hammer / shooting star
    if lw > 2 * b and uw < b:
        return "hammer"
    if uw > 2 * b and lw < b:
        return "shooting_star"
    # Engulfing (needs 2 bars)
    if len(df) >= 2:
        pb = body.iloc[-2]
        prev_bull = c.iloc[-2] > o.iloc[-2]
        if bull and not prev_bull and b > 1.3 * pb:
            return "bullish_engulfing"
        if not bull and prev_bull and b > 1.3 * pb:
            return "bearish_engulfing"
    # Three soldiers / crows
    if len(df) >= 3:
        last3_bull = [c.iloc[k] > o.iloc[k] for k in (-3, -2, -1)]
        strong = (body.iloc[-3:] > 0.6 * avg_body.iloc[-1]).all()
        if all(last3_bull) and strong:
            return "three_white_soldiers"
        if not any(last3_bull) and strong:
            return "three_black_crows"
    # Marubozu-ish strong body
    if b > 1.5 * avg_body.iloc[-1] and (uw + lw) < 0.3 * b:
        return "strong_bull" if bull else "strong_bear"
    return ""


PATTERN_BIAS = {
    "hammer": 1, "bullish_engulfing": 1, "three_white_soldiers": 1, "strong_bull": 1,
    "shooting_star": -1, "bearish_engulfing": -1, "three_black_crows": -1, "strong_bear": -1,
    "doji": 0,
}


# ----------------------------------------------------------------------------
# aggregate
# ----------------------------------------------------------------------------
def compute_all(df):
    """Return latest scalar values + a few helper series for the decision engine."""
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]
    n = len(df)

    ema9, ema21, ema50 = ema(c, 9), ema(c, 21), ema(c, 50)
    macd_line, macd_sig, macd_hist = macd(c)
    adx_line, plus_di, minus_di = adx(h, l, c)
    st_dir = supertrend(h, l, c)
    psar = parabolic_sar(h, l)
    tenkan, kijun, sen_a, sen_b = ichimoku(h, l, c)

    rsi14 = rsi(c)
    stoch_k, stoch_d = stochastic(h, l, c)
    srsi = stoch_rsi(c)
    cci20 = cci(h, l, c)
    willr = williams_r(h, l, c)
    roc9 = roc(c)
    mfi14 = mfi(h, l, c, v)

    bb_u, bb_m, bb_l, bb_w, bb_pb = bollinger(c)
    atr14 = atr(h, l, c)
    kc_u, kc_m, kc_l = keltner(h, l, c)
    dc_u, dc_m, dc_l = donchian(h, l)

    obv_line = obv(c, v)
    vwap_line = vwap(h, l, c, v)

    cloud_top = pd.concat([sen_a, sen_b], axis=1).max(axis=1)
    cloud_bot = pd.concat([sen_a, sen_b], axis=1).min(axis=1)

    return {
        "n": n,
        "close": _last(c),
        # trend
        "ema9": _last(ema9), "ema21": _last(ema21), "ema50": _last(ema50),
        "macd": _last(macd_line), "macd_signal": _last(macd_sig), "macd_hist": _last(macd_hist),
        "adx": _last(adx_line), "plus_di": _last(plus_di), "minus_di": _last(minus_di),
        "supertrend_dir": _last(st_dir, 0),
        "psar": _last(psar), "psar_below": _last(psar) < _last(c),
        "tenkan": _last(tenkan), "kijun": _last(kijun),
        "cloud_top": _last(cloud_top), "cloud_bot": _last(cloud_bot),
        # momentum
        "rsi": _last(rsi14), "stoch_k": _last(stoch_k), "stoch_d": _last(stoch_d),
        "stoch_rsi": _last(srsi), "cci": _last(cci20), "williams_r": _last(willr),
        "roc": _last(roc9), "mfi": _last(mfi14),
        # volatility
        "bb_pb": _last(bb_pb), "bb_width": _last(bb_w),
        "bb_upper": _last(bb_u), "bb_lower": _last(bb_l),
        "atr": _last(atr14),
        "kc_upper": _last(kc_u), "kc_lower": _last(kc_l),
        "dc_upper": _last(dc_u), "dc_lower": _last(dc_l),
        # volume
        "obv_slope": _last(obv_line) - _last(obv_line.shift(3)) if n > 3 else 0.0,
        "vwap": _last(vwap_line),
        # pattern
        "pattern": detect_pattern(df),
    }
