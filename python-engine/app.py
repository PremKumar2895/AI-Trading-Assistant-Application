"""
AI Trading Assistant — analysis engine (v2, REST).

No screen capture / OCR / vision. The user selects an asset; the engine fetches
REAL OHLCV from Crypto.com (crypto) or Yahoo (forex/stocks/indices/commodities),
runs the full indicator confluence across every timeframe, classifies the
strategy, computes entry/exit, and returns one structured report.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from concurrent.futures import ThreadPoolExecutor
import threading
import uvicorn
import time

from providers import DataRouter
from providers.search import search as symbol_search
from ohlcv import from_provider_ohlcv
from decision_engine import decide
from analysis_engine import (
    enrich_indicators, compute_entry_exit, aggregate_timeframes, build_report,
)
from chart_data import build_chart_payload
from tracking import Tracker
from outcome import OutcomeTracker, tf_to_seconds
import playbook
import backtest_strategy

app = FastAPI(title="AI Trading Engine v2")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

data_router = DataRouter()
tracker = Tracker()
outcome_tracker = OutcomeTracker()

DEFAULT_TFS = ["1m", "5m", "15m", "30m", "1h", "1d"]
_last_logged = {"key": None, "ts": 0.0}


def _latest_price(symbol):
    """Latest price for a symbol (used by the outcome settler)."""
    try:
        recs, _ = data_router.get(symbol, "1m")
        if recs:
            return float(recs[-1]["close"])
    except Exception:
        pass
    return None


def _outcome_settler():
    """Background loop: settle matured signals per-symbol, persistently."""
    while True:
        try:
            now = time.time()
            for sid, sym, dirn, entry, epoch in outcome_tracker.due(now):
                price = _latest_price(sym)
                if price is not None:
                    res = OutcomeTracker.result_for(dirn, entry, price)
                    tracker.record_outcome(sid, price, res)
                    outcome_tracker.remove(sid)
                elif now - epoch > outcome_tracker._grace:
                    outcome_tracker.remove(sid)   # unmeasurable — drop
        except Exception as e:
            print(f"settler error: {e}")
        time.sleep(30)


@app.on_event("startup")
def _start_settler():
    threading.Thread(target=_outcome_settler, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "healthy", "port": 8000, "version": 2}


@app.get("/search")
def search(q: str = "", limit: int = 12):
    return {"results": symbol_search(q, limit=limit)}


class AnalyzeReq(BaseModel):
    symbol: str
    timeframes: list[str] | None = None


def _analyze_tf(symbol, tf):
    """Fetch one timeframe of real data and run the decision engine on it."""
    recs, source = data_router.get(symbol, tf)
    if not recs or len(recs) < 30:
        return None
    last_ts = recs[-1].get("t") if isinstance(recs[-1], dict) else None
    df = from_provider_ohlcv(recs)
    price = float(df["close"].iloc[-1])
    ctx = {"symbol": symbol, "timeframe": tf, "current_price": str(price)}
    r = decide(df, context=ctx)
    age_min = round((time.time() - last_ts) / 60, 1) if last_ts else None
    return {
        "tf": tf,
        "signal": r.get("signal"),
        "score": r.get("setup_score"),
        "trend": r.get("trend", "NEUTRAL"),
        "confidence": r.get("confidence"),
        "indicators": enrich_indicators(r.get("indicators")),
        "levels": r.get("levels") or {},
        "pattern": r.get("pattern", ""),
        "reason": r.get("reason", ""),
        "model_prob": r.get("model_prob"),
        "model_eligible": r.get("model_eligible"),
        "age_min": age_min,
        "_df": df,
        "_atr": (r.get("debug_info") or {}).get("atr"),
        "_adx": (r.get("debug_info") or {}).get("adx"),
        "_decision": r,
        "source": source,
        "price": price,
    }


def _maybe_log(symbol, primary_tf, overall, entry, price):
    """Log a confirmed real signal once (debounced) and schedule its outcome.

    Only MEDIUM/HIGH calls are tracked — low-confidence leans don't count toward
    the win-rate, keeping the track record honest.
    """
    if overall["signal"] not in ("BUY", "SELL"):
        return
    if overall.get("confidence") not in ("MEDIUM", "HIGH"):
        return
    if overall.get("stale"):
        return  # never log/track signals on stale (market-closed) data
    # Debounce on symbol+direction over 5 min so an unchanged setup isn't re-logged
    # every refresh (that was inflating the signal count).
    key = (symbol, overall["signal"])
    now = time.time()
    if key == _last_logged["key"] and now - _last_logged["ts"] < 300:
        return
    _last_logged["key"], _last_logged["ts"] = key, now
    try:
        result = {
            "signal": overall["signal"],
            "confidence": overall["confidence"],
            "setup_score": overall.get("aligned", 0),
            "trade_setup": {"expiry_time": entry.get("expiry")},
        }
        ctx = {"symbol": symbol, "timeframe": primary_tf, "current_price": str(price)}
        sid = tracker.log_signal(result, ctx)
        if sid:
            outcome_tracker.add(sid, symbol, overall["signal"], str(price),
                                now + tf_to_seconds(primary_tf))
    except Exception as e:
        print(f"log error: {e}")


@app.post("/analyze")
def analyze(req: AnalyzeReq, log: bool = True):
    t0 = time.perf_counter()
    symbol = (req.symbol or "").strip()
    tfs = req.timeframes or DEFAULT_TFS
    if not symbol:
        return {"error": "no symbol", "signal": "INFO",
                "reason": "Search and select an asset to analyse."}

    # Fetch + analyse every timeframe in parallel (network-bound) to keep /analyze fast.
    uniq = list(dict.fromkeys(tfs))
    with ThreadPoolExecutor(max_workers=min(8, len(uniq))) as pool:
        results = list(pool.map(lambda tf: _analyze_tf(symbol, tf), uniq))
    per_tf = [r for r in results if r]
    source = per_tf[0]["source"] if per_tf else None

    if not per_tf:
        return {
            "symbol": symbol, "signal": "INFO", "confidence": "LOW",
            "reason": f"No live data feed found for '{symbol}'. Try another symbol "
                      f"from the search results.",
            "timeframes": [],
        }

    price = per_tf[0]["price"]   # outcomes are settled by the background thread now
    overall = aggregate_timeframes(per_tf)

    # ---- staleness / market-closed detection ----
    # Use the freshest bar across timeframes. If it is much older than the shortest
    # timeframe (e.g. weekend FX, after-hours stocks, dead feed), the data is stale —
    # the signal can't change, so we must NOT present it as a live, actionable call.
    ages = [p["age_min"] for p in per_tf if p.get("age_min") is not None]
    freshest_age = min(ages) if ages else None
    shortest_tf_s = min(tf_to_seconds(p["tf"]) for p in per_tf)
    stale_thresh_min = max(10, (2 * shortest_tf_s) / 60)
    stale = freshest_age is not None and freshest_age > stale_thresh_min
    overall["stale"] = stale
    overall["data_age_min"] = freshest_age
    if stale:
        # demote to no-trade: the market is closed / the feed is frozen
        overall["signal"] = "WAIT"
        overall["confidence"] = "LOW"

    # primary timeframe = first requested (or 1m); used for entry/exit + chart
    primary = per_tf[0]
    entry = compute_entry_exit(primary["_df"], primary["_atr"], primary["levels"],
                               overall["signal"], primary["tf"])

    # ---- principles playbook: strategy choice + expectancy gate ----
    avg_score = sum((p["score"] or 0) for p in per_tf) / len(per_tf)
    pb = playbook.apply(
        direction=overall["signal"], confidence=overall["confidence"],
        adx=primary["_adx"], price=price, levels=primary["levels"], atr=primary["_atr"],
        pattern=primary.get("pattern"), aligned=overall["aligned"], n=overall["n"],
        avg_score=avg_score, risk_reward=(entry or {}).get("risk_reward"),
        model_prob=primary.get("model_prob"),
    )
    # apply the expectancy gate (may demote a thin-edge call to a LOW lean)
    overall["confidence"] = pb["gated_confidence"]
    overall["win_prob"] = pb["win_prob"]
    overall["binary_ev"] = pb["binary_ev"]
    overall["spot_ev_r"] = pb["spot_ev_r"]
    strategy = (pb["strategy"]["name"], pb["strategy"]["description"])

    chart = build_chart_payload(primary["_df"], primary["levels"],
                                overall["signal"], primary["trend"])

    if log:
        _maybe_log(symbol, primary["tf"], overall, entry, price)
    stats = tracker.stats()
    stats["pending"] = outcome_tracker.pending_count()

    report = build_report(symbol, overall, strategy, per_tf, entry, pb)

    # strip internal keys before serialising
    tf_out = []
    for p in per_tf:
        tf_out.append({k: v for k, v in p.items()
                       if not k.startswith("_") and k != "price"} | {"price": _fmt(p["price"])})

    return {
        "symbol": symbol,
        "price": _fmt(price),
        "asof": time.strftime("%H:%M:%S"),
        "data_source": source,
        "overall": overall,
        "strategy": {"name": strategy[0], "description": strategy[1]},
        "playbook": {
            "location": pb["location"],
            "pattern": pb["pattern"],
            "win_prob": pb["win_prob"],
            "binary_ev": pb["binary_ev"],
            "spot_ev_r": pb["spot_ev_r"],
            "breakeven_winrate": pb["breakeven_winrate"],
            "principles": pb["principles"],
            "gate_note": pb["gate_note"],
        },
        "entry": entry,
        "timeframes": tf_out,
        "chart": chart,
        "model": {"prob": primary.get("model_prob"), "eligible": primary.get("model_eligible")},
        "report": report,
        "stats": stats,
        "latency_ms": int((time.perf_counter() - t0) * 1000),
    }


def _fmt(p):
    a = abs(p)
    return round(p, 2) if a >= 1000 else round(p, 3) if a >= 10 else round(p, 5)


# ---------------------------------------------------------------- backtest
class BacktestReq(BaseModel):
    symbol: str
    timeframes: list[str] | None = None
    horizon: int | None = None


@app.post("/backtest")
def backtest(req: BacktestReq):
    """Replay history through the live decision engine and measure real edge."""
    symbol = (req.symbol or "").strip()
    tfs = req.timeframes or ["5m", "15m", "1h", "1d"]
    horizon = req.horizon or backtest_strategy.HORIZON
    if not symbol:
        return {"error": "no symbol"}

    def one(tf):
        recs, src = data_router.get(symbol, tf)
        if not recs or len(recs) < 80:
            return None
        df = from_provider_ohlcv(recs)
        m, trades = backtest_strategy.backtest_series(df, horizon=horizon)
        if not m:
            return None
        m["tf"] = tf
        m["calibration"] = backtest_strategy.calibration_table(trades)
        m["bars"] = len(df)
        return m

    with ThreadPoolExecutor(max_workers=min(6, len(tfs))) as pool:
        per = [r for r in pool.map(one, list(dict.fromkeys(tfs))) if r]

    if not per:
        return {"symbol": symbol, "error": "not enough history to backtest this asset."}

    # pooled summary
    tot_t = sum(p["trades"] for p in per)
    tot_w = sum(p["wins"] for p in per)
    tot_l = sum(p["losses"] for p in per)
    tot_r = round(sum(p["total_r"] for p in per), 2)
    wr = round(100 * tot_w / (tot_w + tot_l), 1) if (tot_w + tot_l) else None
    exp = round(sum(p["expectancy_r"] * p["trades"] for p in per) / tot_t, 3) if tot_t else None
    summary = {
        "trades": tot_t, "wins": tot_w, "losses": tot_l,
        "win_rate": wr, "expectancy_r": exp, "total_r": tot_r,
        "binary_ev": round((wr / 100) * backtest_strategy.PAYOUT - (1 - wr / 100), 3) if wr is not None else None,
        "horizon": horizon,
    }
    return {"symbol": symbol, "summary": summary, "per_tf": per}


# ---------------------------------------------------------------- scanner
DEFAULT_WATCHLIST = ["BTC/USD", "ETH/USD", "EUR/USD", "GBP/USD", "USD/JPY",
                     "AUD/USD", "AAPL", "TSLA", "GC=F"]


class ScanReq(BaseModel):
    symbols: list[str] | None = None
    timeframes: list[str] | None = None


@app.post("/scan")
def scan(req: ScanReq):
    """Rank a watchlist by setup quality (positive-EV, live, aligned first)."""
    symbols = req.symbols or DEFAULT_WATCHLIST
    tfs = req.timeframes or ["5m", "15m", "1h"]

    def one(sym):
        try:
            r = analyze(AnalyzeReq(symbol=sym, timeframes=tfs), log=False)
            if r.get("signal") == "INFO" or r.get("error"):
                return None
            o = r["overall"]
            return {
                "symbol": sym, "signal": o["signal"], "confidence": o["confidence"],
                "bias": o["bias"], "alignment": o["alignment"], "strength": o.get("strength", 0),
                "win_prob": o.get("win_prob"), "binary_ev": o.get("binary_ev"),
                "stale": o.get("stale", False), "strategy": r["strategy"]["name"],
                "price": r["price"],
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [r for r in pool.map(one, symbols) if r]

    def rank(r):
        live = 0 if r["stale"] else 1
        actionable = 1 if r["signal"] in ("BUY", "SELL") and not r["stale"] else 0
        return (live, actionable, r.get("binary_ev") or -9, r.get("win_prob") or 0)

    rows.sort(key=rank, reverse=True)
    return {"results": rows}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
