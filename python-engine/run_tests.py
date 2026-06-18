"""
Dependency-free regression test suite.

Run:  python run_tests.py     (no pytest needed — prints PASS/FAIL, exits nonzero on failure)
  or:  pytest run_tests.py    (pytest discovers the test_* functions too)

Covers the bugs that have actually shipped before: RSI=50 on pure gains, win-rate
counting flats, cross-symbol settlement, the aggregate direction/HTF logic, the EV
gate, entry/exit geometry, and the R-path scorer.
"""
import os
import tempfile

import numpy as np
import pandas as pd

import indicators as ta
import analysis_engine as ae
import playbook
import backtest_strategy as bts
from outcome import OutcomeTracker, tf_to_seconds
from tracking import Tracker


def _df(closes, vol=1000.0):
    closes = np.asarray(closes, dtype=float)
    o = np.concatenate([[closes[0]], closes[:-1]])
    h = np.maximum(o, closes) + 0.5
    l = np.minimum(o, closes) - 0.5
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": closes,
                         "volume": np.full(len(closes), vol)})


# ---------------- indicators ----------------
def test_rsi_bounds_and_pure_gain():
    r = ta.rsi(pd.Series(np.linspace(1, 50, 60)))          # strictly rising
    assert 95 <= r.iloc[-1] <= 100, f"pure-gain RSI should be ~100, got {r.iloc[-1]}"
    r2 = ta.rsi(pd.Series([10.0] * 40))                    # flat → 50
    assert abs(r2.iloc[-1] - 50) < 1e-6
    rr = ta.rsi(pd.Series(np.random.rand(80) * 10 + 5))
    assert rr.between(0, 100).all()


def test_ema_tracks_trend():
    e = ta.ema(pd.Series(np.linspace(1, 100, 50)), 9)
    assert e.iloc[-1] > e.iloc[0] and e.iloc[-1] < 100


def test_atr_positive():
    df = _df(np.cumsum(np.random.randn(60)) + 100)
    assert ta.atr(df["high"], df["low"], df["close"]).iloc[-1] > 0


def test_supertrend_direction_values():
    df = _df(np.cumsum(np.random.randn(80)) + 100)
    d = ta.supertrend(df["high"], df["low"], df["close"])
    assert set(np.unique(d.to_numpy())).issubset({-1.0, 1.0})


def test_compute_all_keys():
    df = _df(np.cumsum(np.random.randn(60)) + 100)
    ind = ta.compute_all(df)
    for k in ("rsi", "adx", "atr", "ema9", "macd_hist", "pattern"):
        assert k in ind


# ---------------- aggregate_timeframes (the win-rate lever) ----------------
def test_aggregate_all_buy():
    per = [{"tf": t, "signal": "BUY", "score": 75, "trend": "BULLISH"} for t in ("1m", "5m", "1h")]
    o = ae.aggregate_timeframes(per)
    assert o["signal"] == "BUY" and o["bias"] == "BULLISH"


def test_aggregate_empty_waits():
    assert ae.aggregate_timeframes([])["signal"] == "WAIT"


def test_daily_dominates():
    # noisy 1m/5m BUY vs strong daily SELL → daily wins
    per = [{"tf": "1m", "signal": "BUY", "score": 70, "trend": "BULLISH"},
           {"tf": "5m", "signal": "BUY", "score": 60, "trend": "BULLISH"},
           {"tf": "1d", "signal": "SELL", "score": 85, "trend": "BEARISH"}]
    o = ae.aggregate_timeframes(per)
    assert o["signal"] == "SELL", f"daily should dominate, got {o['signal']}"


def test_htf_conflict_demotes():
    # lower TFs strongly buy, weak daily sells → BUY but demoted (against major trend)
    per = [{"tf": "1m", "signal": "BUY", "score": 90, "trend": "BULLISH"},
           {"tf": "5m", "signal": "BUY", "score": 90, "trend": "BULLISH"},
           {"tf": "15m", "signal": "BUY", "score": 90, "trend": "BULLISH"},
           {"tf": "1d", "signal": "SELL", "score": 55, "trend": "BEARISH"}]
    o = ae.aggregate_timeframes(per)
    assert o["signal"] == "BUY" and o["htf_conflict"] is True and o["confidence"] == "LOW"


def test_tf_weight_monotonic():
    assert ae._tf_weight("1m") < ae._tf_weight("1h") < ae._tf_weight("1d")


# ---------------- entry/exit geometry ----------------
def test_entry_exit_buy_sell_geometry():
    df = _df(np.cumsum(np.random.randn(60)) + 100)
    b = ae.compute_entry_exit(df, atr=1.0, levels={}, signal="BUY", tf="5m")
    assert b["stop"] < b["entry"] < b["target"] and b["risk_reward"] >= 1.5
    s = ae.compute_entry_exit(df, atr=1.0, levels={}, signal="SELL", tf="5m")
    assert s["target"] < s["entry"] < s["stop"]


def test_entry_exit_atr_floor():
    df = _df([100.0] * 60)                                   # flat → tiny ATR
    b = ae.compute_entry_exit(df, atr=0.0, levels={}, signal="BUY", tf="5m")
    assert abs(b["entry"] - b["stop"]) > 0                    # floor kept a real distance


# ---------------- playbook EV gate ----------------
def test_playbook_low_edge_demoted():
    pb = playbook.apply(direction="BUY", confidence="MEDIUM", adx=10, price=100,
                        levels={"support": 98, "resistance": 101}, atr=1.0,
                        pattern="", aligned=2, n=4, avg_score=35,
                        risk_reward=0.8, model_prob=None)
    # win-prob below break-even AND spot EV<=0 → gated to a LOW lean with a note
    assert pb["win_prob"] <= pb["breakeven_winrate"], f"win_prob {pb['win_prob']}"
    assert pb["gated_confidence"] == "LOW" and pb["gate_note"]


def test_playbook_pattern_and_location():
    assert playbook.pattern_meta("hammer")["bias"] == 1
    assert playbook.price_location(100, 99.9, 110, 1.0) == "at_support"
    assert playbook.price_location(100, 90, 100.1, 1.0) == "at_resistance"


# ---------------- outcome settlement (symbol-aware) ----------------
def test_outcome_result_for():
    rf = OutcomeTracker.result_for
    assert rf("BUY", 100, 101) == "win" and rf("BUY", 100, 99) == "loss"
    assert rf("SELL", 100, 99) == "win" and rf("SELL", 100, 101) == "loss"
    assert rf("BUY", 100, 100) == "flat"


def test_tf_to_seconds():
    assert tf_to_seconds("5m") == 300 and tf_to_seconds("1h") == 3600
    assert tf_to_seconds("1d") == 86400 and tf_to_seconds("30s") == 30


# ---------------- tracking win-rate excludes flats ----------------
def test_winrate_excludes_flats():
    tmp = os.path.join(tempfile.gettempdir(), "test_signals.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    tr = Tracker(db_path=tmp)
    for res in ("win", "loss", "flat"):
        sid = tr.log_signal({"signal": "BUY", "confidence": "HIGH", "setup_score": 70},
                            {"symbol": "X", "timeframe": "5m", "current_price": "1"})
        tr.record_outcome(sid, "1", res)
    s = tr.stats()
    tr.close()
    os.remove(tmp)
    assert s["settled"] == 3 and s["flats"] == 1
    assert s["win_rate"] == 50.0, f"1 win / (1 win+1 loss) = 50%, got {s['win_rate']}"


# ---------------- R-path scorer ----------------
def test_r_path_target_and_stop():
    # BUY, atr=1 → stop=-1.5, target=+3.0; highs reach target first
    R = bts._r_path("BUY", 100.0, 1.0, highs=[100, 104], lows=[99.9, 99.8], closes=[100, 104])
    assert R == bts.TGT_R / bts.STOP_R                       # +2R
    R2 = bts._r_path("BUY", 100.0, 1.0, highs=[100, 100], lows=[97, 97], closes=[98, 98])
    assert R2 == -1.0                                        # stop hit → -1R


# ---------------- runner ----------------
def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed ({len(tests)} total)")
    return failed


if __name__ == "__main__":
    import sys
    sys.exit(1 if _run() else 0)
