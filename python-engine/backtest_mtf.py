"""
Multi-timeframe backtest — measures the COMBINED signal the app actually shows.

The per-TF backtester (backtest_strategy.py) only scores single-timeframe decide()
calls. But live, the user sees `aggregate_timeframes(...)` — daily-weighted, with the
higher-TF trend filter (#13). This replays *that* combined call through history:

  1. fetch each timeframe's OHLCV (with bar timestamps),
  2. precompute decide() once per bar of each TF (memoised — no redundant work),
  3. walk the BASE timeframe; at each bar align every TF to its last completed bar,
     run aggregate_timeframes() → the same combined call shown live,
  4. score the outcome over `horizon` base bars (binary + ATR R-path),
  5. report overall AND by confidence bucket (so we can see HIGH > MEDIUM > LOW —
     i.e. whether the gating actually sorts good trades from bad).

No look-ahead: every TF is sliced to bars at/earlier than the base bar's time.
"""
import numpy as np

from decision_engine import decide
from analysis_engine import aggregate_timeframes
import backtest_strategy as bts

WARMUP = 50
HORIZON = 4


def _verdicts(df, warmup=WARMUP):
    """Per-bar single-TF verdict for every bar (memoised once per TF)."""
    out = [None] * len(df)
    for j in range(warmup, len(df)):
        r = decide(df.iloc[: j + 1], use_model=False)
        out[j] = {"signal": r.get("signal"), "score": r.get("setup_score") or 0,
                  "trend": r.get("trend", "NEUTRAL")}
    return out


def backtest_mtf(tf_data, base_tf, horizon=HORIZON, only_confident=False):
    """tf_data: {tf: (df, ts_array)}. Returns (metrics, by_confidence, trades).

    base_tf must be the shortest TF (outcomes are scored on it).
    """
    if base_tf not in tf_data:
        return None, {}, []
    base_df, base_ts = tf_data[base_tf]
    n = len(base_df)
    if n < WARMUP + horizon + 5:
        return None, {}, []

    # precompute per-TF verdicts + sorted timestamps
    verds = {tf: _verdicts(df) for tf, (df, ts) in tf_data.items()}
    ts_arr = {tf: ts for tf, (df, ts) in tf_data.items()}

    close = base_df["close"].to_numpy()
    high = base_df["high"].to_numpy()
    low = base_df["low"].to_numpy()

    trades = []
    for i in range(WARMUP, n - horizon):
        t_i = base_ts[i]
        per_tf = []
        for tf, (df, ts) in tf_data.items():
            j = int(np.searchsorted(ts, t_i, side="right")) - 1   # last completed bar
            if j < WARMUP or j >= len(verds[tf]) or verds[tf][j] is None:
                continue
            v = verds[tf][j]
            per_tf.append({"tf": tf, "signal": v["signal"], "score": v["score"],
                           "trend": v["trend"]})
        if len(per_tf) < 2:
            continue
        agg = aggregate_timeframes(per_tf)
        sig = agg["signal"]
        if sig not in ("BUY", "SELL"):
            continue
        if only_confident and agg["confidence"] == "LOW":
            continue

        entry = float(close[i])
        future = float(close[i + horizon])
        binv = "flat" if entry == future else ("win" if (future > entry) == (sig == "BUY") else "loss")
        # reuse the same ATR R-path as the single-TF backtester
        atr = (decide(base_df.iloc[: i + 1], use_model=False).get("debug_info") or {}).get("atr")
        R = bts._r_path(sig, entry, atr,
                        high[i + 1: i + 1 + horizon], low[i + 1: i + 1 + horizon],
                        close[i + 1: i + 1 + horizon])
        trades.append({"i": i, "side": sig, "conf": agg["confidence"],
                       "binary": binv, "R": round(float(R), 3)})

    metrics = bts._aggregate(trades)
    by_conf = {}
    for conf in ("HIGH", "MEDIUM", "LOW"):
        sub = [t for t in trades if t["conf"] == conf]
        if sub:
            by_conf[conf] = bts._aggregate(sub)
    return metrics, by_conf, trades
