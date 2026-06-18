"""
Training pipeline for the self-learning trade model.

Pulls real historical OHLCV from Crypto.com across several instruments/timeframes,
self-labels each bar by what price did `HORIZON` bars later, then does a
walk-forward (chronological, per-series) split — train / calibrate / test — so the
model is always evaluated on data it has never seen *from its future*. Calibrates
with isotonic regression and runs an EV backtest that decides eligibility.

Run:  python train.py
"""
import json
import sys
import time
import urllib.request

import numpy as np
import pandas as pd

from features import build_features, FEATURE_NAMES
from labeling import make_labels, make_barrier_labels
from model import TradeModel
from backtest import best_threshold, ev_backtest
from providers.yahoo import YahooProvider

BASE = "https://api.crypto.com/exchange/v1/public/get-candlestick"
# Real crypto pairs from the exchange.
INSTRUMENTS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT",
               "ADA_USDT", "DOGE_USDT", "LTC_USDT",
               "AVAX_USDT", "LINK_USDT", "DOT_USDT"]
# Real forex + equities via Yahoo, so the model also learns non-crypto regimes
# (the assets users actually trade on Binomo / brokers).
FOREX = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "EUR/JPY"]
STOCKS = ["AAPL", "MSFT", "TSLA", "AMZN", "GOOGL", "NVDA"]
TIMEFRAMES = ["1m", "5m", "15m"]
HORIZON = 1          # predict next-bar direction (the binary-option bet)
PAYOUT = 0.85        # typical binary payout; EV must beat this
COUNT = 1000         # ask for more crypto history per series

_yahoo = YahooProvider(ttl=0.0)


def fetch(inst, tf, count=COUNT):
    url = f"{BASE}?instrument_name={inst}&timeframe={tf}&count={count}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.load(r)
        rows = (d.get("result") or {}).get("data") or []
        if not rows:
            return None
        df = pd.DataFrame(
            {
                "open": [float(x["o"]) for x in rows],
                "high": [float(x["h"]) for x in rows],
                "low": [float(x["l"]) for x in rows],
                "close": [float(x["c"]) for x in rows],
                "volume": [float(x.get("v", 0.0)) for x in rows],
            }
        )
        return df
    except Exception as e:
        print(f"  fetch failed {inst} {tf}: {e}")
        return None


def fetch_yahoo(symbol, tf):
    """Forex / equity history via Yahoo -> same OHLCV DataFrame shape."""
    recs = _yahoo.get_ohlcv(symbol, tf, limit=500)
    if not recs:
        return None
    return pd.DataFrame(recs)


def _split_series(df, Xtr, ytr, Xca, yca, Xte, yte):
    """Append one series' walk-forward split to the pooled lists. Returns 1 if used."""
    if df is None or len(df) < 120:
        return 0
    feats = build_features(df)
    # ML v2: triple-barrier target (decisive +/-0.5 ATR move) — more learnable than next-bar.
    labels = make_barrier_labels(df, horizon=6, k=0.5)
    data = feats.copy()
    data["y"] = labels
    data = data.dropna()
    if len(data) < 80:
        return 0
    X = data[FEATURE_NAMES].values
    y = data["y"].values
    n = len(X)
    i_tr = int(n * 0.6)      # 60% train
    i_ca = int(n * 0.75)     # next 15% calibration ; last 25% test
    Xtr.append(X[:i_tr]); ytr.append(y[:i_tr])
    Xca.append(X[i_tr:i_ca]); yca.append(y[i_tr:i_ca])
    Xte.append(X[i_ca:]); yte.append(y[i_ca:])
    return 1


def build_dataset():
    """Per-series chronological split -> pooled (train, calib, test)."""
    Xtr, ytr, Xca, yca, Xte, yte = [], [], [], [], [], []
    series = 0

    print("  crypto (crypto.com)...")
    for inst in INSTRUMENTS:
        for tf in TIMEFRAMES:
            series += _split_series(fetch(inst, tf), Xtr, ytr, Xca, yca, Xte, yte)
            time.sleep(0.05)       # be gentle to the API

    print("  forex + stocks (yahoo)...")
    for sym in FOREX + STOCKS:
        for tf in TIMEFRAMES:
            series += _split_series(fetch_yahoo(sym, tf), Xtr, ytr, Xca, yca, Xte, yte)
            time.sleep(0.05)

    if not Xtr:
        return None
    pack = lambda L: np.vstack(L)
    cat = lambda L: np.concatenate(L)
    print(f"\nSeries used: {series}")
    return (pack(Xtr), cat(ytr), pack(Xca), cat(yca), pack(Xte), cat(yte))


def main():
    print("Fetching real historical OHLCV and self-labelling...")
    ds = build_dataset()
    if ds is None:
        print("No data fetched — aborting.")
        sys.exit(1)
    Xtr, ytr, Xca, yca, Xte, yte = ds
    print(f"Samples — train {len(ytr)}, calib {len(yca)}, test {len(yte)}")
    print(f"Train class balance (up): {ytr.mean():.3f}")

    model = TradeModel()
    model.fit(Xtr, ytr)
    model.calibrate(Xca, yca)

    p_test = model.proba_up(Xte)

    # Honest out-of-sample metrics.
    try:
        from sklearn.metrics import roc_auc_score, accuracy_score
        auc = roc_auc_score(yte, p_test)
        acc = accuracy_score(yte, (p_test >= 0.5).astype(int))
    except Exception:
        auc = float("nan")
        acc = float(np.mean((p_test >= 0.5).astype(int) == yte))

    best = best_threshold(p_test, yte, payout=PAYOUT)
    model.metrics = {
        "auc": round(float(auc), 4), "accuracy": round(float(acc), 4),
        "n_test": int(len(yte)), "horizon": HORIZON, **best,
        "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    model.eligible = bool(best["ev_per_trade"] is not None and best["ev_per_trade"] > 0)

    path = model.save()
    print("\n================ TRAINING REPORT ================")
    print(f"AUC (out-of-sample):     {model.metrics['auc']}  (0.5 = no skill)")
    print(f"Accuracy @0.5:           {model.metrics['accuracy']}")
    print(f"Best threshold:          {best['threshold']}")
    print(f"  trades:                {best['trades']} ({best.get('coverage')*100:.1f}% coverage)")
    print(f"  win-rate:              {best['win_rate']}")
    print(f"  break-even needed:     {best.get('breakeven_winrate')} (payout {PAYOUT})")
    print(f"  EV / trade:            {best['ev_per_trade']}")
    print(f"ELIGIBLE to elevate:     {model.eligible}")
    if not model.eligible:
        print("  -> Model does NOT beat the payout out-of-sample. It will be shown")
        print("     for transparency but will NOT upgrade signals. This is the honest")
        print("     result for next-bar prediction on efficient markets.")
    print(f"Saved: {path}")
    print("=================================================")


if __name__ == "__main__":
    main()
