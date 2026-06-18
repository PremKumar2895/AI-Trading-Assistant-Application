"""Deep backtest across a diverse basket → measured edge + win-prob calibration."""
import json
import sys
from collections import defaultdict

from providers import DataRouter
from ohlcv import from_provider_ohlcv
import backtest_strategy as bt

ROUTER = DataRouter()
BASKET = ["BTC/USD", "ETH/USD", "SOL/USD",                  # crypto (24/7, deep)
          "EUR/USD", "GBP/USD", "USD/JPY",                  # forex
          "AAPL", "TSLA", "NVDA"]                           # stocks
TFS = ["15m", "1h", "1d"]
LIMIT = 200
STEP = 2


def main():
    all_trades = []
    rows = []
    for sym in BASKET:
        for tf in TFS:
            recs, src = ROUTER.get(sym, tf, limit=LIMIT)
            if not recs or len(recs) < 90:
                continue
            df = from_provider_ohlcv(recs)
            m, trades = bt.backtest_series(df, step=STEP)
            if not m or m["trades"] == 0:
                continue
            all_trades.extend(trades)
            rows.append((sym, tf, src, m))
            print(f"{sym:8s} {tf:4s} [{src:9s}] "
                  f"trades={m['trades']:3d} wr={m['win_rate']} "
                  f"exp={m['expectancy_r']}R pf={m['profit_factor']} "
                  f"maxDD={m['max_drawdown_r']}R EV={m['binary_ev']}", flush=True)

    # pooled
    tw = sum(1 for t in all_trades if t["binary"] == "win")
    tl = sum(1 for t in all_trades if t["binary"] == "loss")
    tf_ = sum(1 for t in all_trades if t["binary"] == "flat")
    Rs = [t["R"] for t in all_trades]
    wr = round(100 * tw / (tw + tl), 1) if (tw + tl) else None
    exp = round(sum(Rs) / len(Rs), 3) if Rs else None
    print("\n================ POOLED (all assets/TFs) ================", flush=True)
    print(f"trades={len(all_trades)} win={tw} loss={tl} flat={tf_}", flush=True)
    print(f"win-rate (excl flats) = {wr}%   expectancy = {exp}R", flush=True)
    if wr is not None:
        print(f"binary EV @0.85 payout = {round((wr/100)*0.85-(1-wr/100),3)} "
              f"(break-even ~54%)", flush=True)

    # calibration table: setup-score bucket -> empirical win-rate
    calib = bt.calibration_table(all_trades)
    print("\nCALIBRATION (setup-score bucket -> win-rate):", flush=True)
    for b, v in calib.items():
        print(f"  {b:8s} n={v['n']:4d}  win_rate={v['win_rate']}", flush=True)

    # persist for the playbook to consume (C)
    out = {"pooled": {"trades": len(all_trades), "win_rate": wr, "expectancy_r": exp},
           "calibration": calib}
    with open("calibration.json", "w") as f:
        json.dump(out, f, indent=2)
    print("\nsaved calibration.json", flush=True)


if __name__ == "__main__":
    main()
