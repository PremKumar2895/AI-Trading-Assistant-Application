"""Deep multi-timeframe backtest — does the combined (daily-weighted) call beat
the single-TF signal? Reports overall + by-confidence so we can see if HIGH > LOW."""
import numpy as np

from providers import DataRouter
from ohlcv import from_provider_ohlcv
import backtest_mtf as mtf
import backtest_strategy as bts

ROUTER = DataRouter()
BASKET = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "AAPL", "TSLA", "NVDA"]
TFS = ["15m", "1h", "1d"]
BASE = "15m"
LIMIT = 220


def fetch_tf_data(sym):
    out = {}
    for tf in TFS:
        recs, src = ROUTER.get(sym, tf, limit=LIMIT)
        if not recs or len(recs) < 70:
            continue
        ts = [r.get("t") for r in recs]
        if any(t is None for t in ts):
            continue
        out[tf] = (from_provider_ohlcv(recs), np.array(ts, dtype=float))
    return out


def main():
    all_trades, single_trades = [], []
    print("symbol   | MTF trades  wr%   exp     | single-TF(base) wr%   exp", flush=True)
    print("-" * 72, flush=True)
    for sym in BASKET:
        td = fetch_tf_data(sym)
        if BASE not in td or len(td) < 2:
            continue
        m, by_conf, trades = mtf.backtest_mtf(td, BASE)
        if not m:
            continue
        all_trades.extend(trades)
        # single-TF baseline on the same base series for comparison
        sm, st = bts.backtest_series(td[BASE][0])
        single_trades.extend(st or [])
        print(f"{sym:8s} | {m['trades']:3d}  wr={m['win_rate']} exp={m['expectancy_r']}R "
              f"| base {sm['trades'] if sm else 0} wr={sm['win_rate'] if sm else None} "
              f"exp={sm['expectancy_r'] if sm else None}R", flush=True)
        for c in ("HIGH", "MEDIUM", "LOW"):
            if c in by_conf:
                b = by_conf[c]
                print(f"           {c:6s}: {b['trades']:3d} wr={b['win_rate']} exp={b['expectancy_r']}R "
                      f"EV={b['binary_ev']}", flush=True)

    print("\n================ POOLED ================", flush=True)
    A = bts._aggregate(all_trades)
    S = bts._aggregate(single_trades)
    print(f"MULTI-TF combined : trades={A['trades']} win-rate={A['win_rate']}% "
          f"expectancy={A['expectancy_r']}R PF={A['profit_factor']} binEV={A['binary_ev']}", flush=True)
    print(f"SINGLE-TF (base)  : trades={S['trades']} win-rate={S['win_rate']}% "
          f"expectancy={S['expectancy_r']}R PF={S['profit_factor']} binEV={S['binary_ev']}", flush=True)

    # by-confidence pooled — the key test: does HIGH beat MEDIUM beat LOW?
    print("\nMULTI-TF by confidence (does gating sort good from bad?):", flush=True)
    for c in ("HIGH", "MEDIUM", "LOW"):
        sub = [t for t in all_trades if t["conf"] == c]
        if sub:
            b = bts._aggregate(sub)
            print(f"  {c:6s}: {b['trades']:3d} trades  wr={b['win_rate']}%  exp={b['expectancy_r']}R  "
                  f"binEV={b['binary_ev']}", flush=True)


if __name__ == "__main__":
    main()
