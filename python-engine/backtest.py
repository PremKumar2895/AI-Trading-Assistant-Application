"""
Out-of-sample EV backtest.

A model is only useful for binary options if it beats the payout. For confident
predictions (proba >= conf for up, <= 1-conf for down) we compute the win rate and
the expected value per unit stake:  EV = win_rate*payout - (1-win_rate).
EV <= 0 means "do not trust to elevate signals", regardless of accuracy.
"""
import numpy as np


def ev_backtest(proba_up, y_true, conf=0.58, payout=0.85):
    proba_up = np.asarray(proba_up, dtype=float)
    y_true = np.asarray(y_true, dtype=float)

    buy = proba_up >= conf
    sell = proba_up <= (1.0 - conf)
    take = buy | sell
    n = int(take.sum())
    if n == 0:
        return {"trades": 0, "win_rate": None, "ev_per_trade": None,
                "payout": payout, "threshold": conf, "coverage": 0.0}

    pred_up = buy[take]
    actual_up = y_true[take] == 1
    wins = int(np.sum((pred_up & actual_up) | (~pred_up & ~actual_up)))
    win_rate = wins / n
    ev = win_rate * payout - (1 - win_rate)
    return {
        "trades": n,
        "win_rate": round(win_rate, 4),
        "ev_per_trade": round(ev, 4),
        "payout": payout,
        "threshold": conf,
        "coverage": round(n / len(y_true), 4),
        "breakeven_winrate": round(1 / (1 + payout), 4),
    }


def best_threshold(proba_up, y_true, payout=0.85,
                   grid=(0.55, 0.58, 0.60, 0.62, 0.65, 0.70), min_trades=30):
    """Pick the threshold with the best EV that still has enough trades."""
    best = None
    for conf in grid:
        r = ev_backtest(proba_up, y_true, conf=conf, payout=payout)
        if r["trades"] < min_trades or r["ev_per_trade"] is None:
            continue
        if best is None or r["ev_per_trade"] > best["ev_per_trade"]:
            best = r
    return best or ev_backtest(proba_up, y_true, conf=0.58, payout=payout)
