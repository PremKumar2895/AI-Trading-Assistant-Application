"""
Strategy backtester — measures whether the rule engine actually has an edge.

Replays historical candles through the SAME `decision_engine.decide` used live, with
no look-ahead (each bar only sees data up to itself). For every fired BUY/SELL it
records two outcomes:
  • binary  — did price close in the signal's direction after `horizon` bars
              (this is the binary-option bet);
  • R-path  — simulate an ATR stop (1.5R) / target (3R); whichever the path hits
              first decides the R-multiple (spot-trading expectancy).

Aggregates win-rate (flats excluded), expectancy (avg R), profit factor, max
drawdown, and a setup-score → win-rate calibration table.
"""
from decision_engine import decide

WARMUP = 60
HORIZON = 3
PAYOUT = 0.85
STOP_R = 1.5
TGT_R = 3.0


def _r_path(side, entry, atr, highs, lows, closes):
    """Simulate stop/target over the forward window; return realised R-multiple."""
    if not atr or atr <= 0:
        return 0.0
    risk = STOP_R * atr
    if side == "BUY":
        stop, tgt = entry - risk, entry + TGT_R * atr
        for h, l in zip(highs, lows):
            if l <= stop:
                return -1.0
            if h >= tgt:
                return TGT_R / STOP_R
        return (closes[-1] - entry) / risk
    else:
        stop, tgt = entry + risk, entry - TGT_R * atr
        for h, l in zip(highs, lows):
            if h >= stop:
                return -1.0
            if l <= tgt:
                return TGT_R / STOP_R
        return (entry - closes[-1]) / risk


def backtest_series(df, horizon=HORIZON, warmup=WARMUP, step=1):
    """Backtest one OHLCV series. Returns (metrics, trades).

    `step` evaluates every Nth bar (step=2 halves cost for the large basket run;
    the per-symbol /backtest endpoint uses step=1 for full resolution).
    """
    n = len(df)
    if n < warmup + horizon + 5:
        return None, []
    close = df["close"].to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()

    trades = []
    for i in range(warmup, n - horizon, step):
        sub = df.iloc[: i + 1]
        r = decide(sub, use_model=False)   # skip info-only ML overlay (fast)
        sig = r.get("signal")
        if sig not in ("BUY", "SELL"):
            continue
        entry = float(close[i])
        future = float(close[i + horizon])
        if entry == future:
            bin = "flat"
        elif (future > entry) == (sig == "BUY"):
            bin = "win"
        else:
            bin = "loss"
        atr = (r.get("debug_info") or {}).get("atr")
        R = _r_path(sig, entry, atr,
                    high[i + 1: i + 1 + horizon], low[i + 1: i + 1 + horizon],
                    close[i + 1: i + 1 + horizon])
        trades.append({
            "i": i, "side": sig, "score": r.get("setup_score") or 0,
            "binary": bin, "R": round(float(R), 3),
        })

    return _aggregate(trades), trades


def _aggregate(trades):
    n = len(trades)
    wins = sum(1 for t in trades if t["binary"] == "win")
    losses = sum(1 for t in trades if t["binary"] == "loss")
    flats = sum(1 for t in trades if t["binary"] == "flat")
    decided = wins + losses
    win_rate = round(100 * wins / decided, 1) if decided else None

    Rs = [t["R"] for t in trades]
    gains = sum(r for r in Rs if r > 0)
    losses_r = sum(r for r in Rs if r < 0)
    expectancy = round(sum(Rs) / n, 3) if n else None
    profit_factor = round(gains / abs(losses_r), 2) if losses_r else (None if not gains else float("inf"))

    # max drawdown of the cumulative-R equity curve
    eq, peak, dd = 0.0, 0.0, 0.0
    for r in Rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    binary_ev = round((win_rate / 100) * PAYOUT - (1 - win_rate / 100), 3) if win_rate is not None else None

    return {
        "trades": n, "wins": wins, "losses": losses, "flats": flats,
        "win_rate": win_rate, "expectancy_r": expectancy,
        "profit_factor": profit_factor, "max_drawdown_r": round(dd, 2),
        "total_r": round(eq, 2), "binary_ev": binary_ev,
    }


def calibration_table(trades):
    """setup-score bucket → empirical win-rate (for grounding win-prob)."""
    buckets = {"0-40": [], "40-55": [], "55-70": [], "70-100": []}
    for t in trades:
        if t["binary"] == "flat":
            continue
        s = t["score"]
        b = "0-40" if s < 40 else "40-55" if s < 55 else "55-70" if s < 70 else "70-100"
        buckets[b].append(1 if t["binary"] == "win" else 0)
    out = {}
    for b, xs in buckets.items():
        out[b] = {"n": len(xs), "win_rate": round(100 * sum(xs) / len(xs), 1) if xs else None}
    return out
