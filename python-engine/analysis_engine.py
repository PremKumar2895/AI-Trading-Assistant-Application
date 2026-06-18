"""
Analysis enrichment layer (v2).

Turns the raw confluence decision into the user-facing report:
  - per-indicator *expected outcome* text,
  - a named trading *strategy* (the method the engine actually used),
  - concrete *entry / stop / target* with risk:reward and expiry,
  - a multi-timeframe *alignment* aggregate (the win-rate lever),
  - a plain, structured *analysis report*.

Pure functions over the dicts that `decision_engine.decide` already returns —
no network, no side effects.
"""
import math
from datetime import datetime, timedelta


def _tf_seconds(tf):
    t = str(tf or "1m").lower().strip()
    n = "".join(ch for ch in t if ch.isdigit()) or "1"
    n = int(n)
    if t.endswith("s"):
        return max(n, 5)
    if t.endswith("h"):
        return n * 3600
    if t.endswith("d"):
        return n * 86400
    return n * 60  # minutes default


def _round(price):
    if price is None:
        return None
    a = abs(price)
    if a >= 1000:
        return round(price, 2)
    if a >= 10:
        return round(price, 3)
    return round(price, 5)


# ---- per-indicator expected outcome -------------------------------------
def expected_outcome(name, vote, detail):
    """One-line 'what this implies next' for an indicator."""
    d = "up" if vote > 0 else "down" if vote < 0 else "sideways"
    bull = vote > 0
    table = {
        "EMA stack": ("Trend aligned up — buy dips" if bull else
                      "Trend aligned down — sell rallies" if vote < 0 else
                      "EMAs tangled — no trend edge"),
        "MACD": "Momentum building up" if bull else "Momentum fading / down" if vote < 0 else "Momentum flat",
        "ADX/DI": "Strong directional trend — favour continuation" if vote else "Weak/ranging — avoid trend trades",
        "Supertrend": "Trailing trend is up" if bull else "Trailing trend is down" if vote < 0 else "Flat",
        "Parabolic SAR": "Dots below — uptrend intact" if bull else "Dots above — downtrend intact",
        "Ichimoku cloud": "Above cloud — bullish structure" if bull else "Below cloud — bearish structure" if vote < 0 else "Inside cloud — indecision",
        "RSI": "Bullish momentum, expect continuation up" if bull else "Bearish momentum, expect downside" if vote < 0 else "Neutral momentum",
        "Stochastic": "Turning up" if bull else "Turning down" if vote < 0 else "Mid-range",
        "Stoch RSI": "Oversold-to-up bias" if bull else "Overbought-to-down bias" if vote < 0 else "Neutral",
        "CCI": "Bullish pressure" if bull else "Bearish pressure" if vote < 0 else "Neutral",
        "Williams %R": "Buyers in control" if bull else "Sellers in control" if vote < 0 else "Balanced",
        "ROC": "Rate of change positive" if bull else "Rate of change negative" if vote < 0 else "Flat",
        "MFI": "Money flowing in" if bull else "Money flowing out" if vote < 0 else "Balanced flow",
        "OBV slope": "Volume confirms up" if bull else "Volume confirms down" if vote < 0 else "Volume flat",
        "VWAP": "Above VWAP — intraday bulls" if bull else "Below VWAP — intraday bears",
        "Bollinger": "At lower band — bounce risk up" if bull else "At upper band — fade risk down" if vote < 0 else "Mid-band",
        "Keltner": "Breakout up" if bull else "Breakdown" if vote < 0 else "Inside channel",
        "Donchian": "New-high breakout" if bull else "New-low breakdown" if vote < 0 else "Mid-range",
        "Candle pattern": f"Pattern leans {d}",
        "Multi-timeframe": f"Higher-TF bias {d}",
    }
    return table.get(name, f"Leans {d}")


def enrich_indicators(indicators):
    """Attach value + expected outcome to each indicator vote for the UI table."""
    out = []
    for ind in indicators or []:
        out.append({
            "name": ind.get("name"),
            "category": ind.get("category"),
            "vote": ind.get("vote"),
            "value": ind.get("detail"),
            "signal": "bull" if ind.get("vote", 0) > 0 else "bear" if ind.get("vote", 0) < 0 else "neutral",
            "expected": expected_outcome(ind.get("name"), ind.get("vote", 0), ind.get("detail")),
        })
    return out


# (strategy classification now lives in playbook.select_playbook — see playbook.py)


# ---- entry / stop / target ----------------------------------------------
def compute_entry_exit(df, atr, levels, signal, tf):
    """Concrete trade levels. ATR-based, snapped to nearby S/R when sensible."""
    if df is None or len(df) == 0:
        return None
    price = float(df["close"].iloc[-1])
    if not atr or atr != atr or atr <= 0:
        # fallback: average true range proxy from recent candles
        rng = (df["high"] - df["low"]).tail(14)
        atr = float(rng.mean()) if len(rng) else price * 0.002
    # Volatility floor: keep stop/target meaningful when 1m ATR collapses (e.g.
    # quiet sessions / closed FX market) — scales across FX, stocks and crypto.
    atr = max(atr, abs(price) * 0.0008)
    sup = levels.get("support") if levels else None
    res = levels.get("resistance") if levels else None

    now = datetime.now()
    expiry = (now + timedelta(seconds=_tf_seconds(tf))).strftime("%H:%M:%S")
    entry_t = now.strftime("%H:%M:%S")

    risk_d = 1.5 * atr          # consistent risk
    reward_d = 3.0 * atr        # baseline 1:2 reward
    if signal == "BUY":
        stop = price - risk_d
        target = price + reward_d
        # extend target to resistance only if it sits *beyond* the baseline (better reward)
        if res and price < res < price + 6 * atr and (res - price) > reward_d:
            target = res
        direction = "UP / CALL"
    elif signal == "SELL":
        stop = price + risk_d
        target = price - reward_d
        if sup and price - 6 * atr < sup < price and (price - sup) > reward_d:
            target = sup
        direction = "DOWN / PUT"
    else:
        return {
            "entry": _round(price), "entry_time": entry_t, "stop": None, "target": None,
            "risk_reward": None, "expiry": expiry, "direction": "—",
        }

    risk = abs(price - stop)
    reward = abs(target - price)
    rr = round(reward / risk, 2) if risk > 0 else None
    return {
        "entry": _round(price),
        "entry_time": entry_t,
        "stop": _round(stop),
        "target": _round(target),
        "risk": _round(risk),
        "reward": _round(reward),
        "risk_reward": rr,
        "expiry": expiry,
        "direction": direction,
    }


# ---- multi-timeframe aggregate ------------------------------------------
import math


def _tf_dir(p):
    """Directional lean of a timeframe: a fired BUY/SELL counts double a trend lean."""
    if p["signal"] == "BUY":
        return 1, 2.0
    if p["signal"] == "SELL":
        return -1, 2.0
    t = p.get("trend")
    if t == "BULLISH":
        return 1, 1.0
    if t == "BEARISH":
        return -1, 1.0
    return 0, 0.0


def _tf_weight(tf):
    """Higher timeframes carry more weight — the backtest showed the real edge is on
    the daily TF, and the books say trade with the *major* trend (Livermore/Murphy).
    Weight grows ~log with the timeframe's duration (1m≈1.0 … 1d≈3.6)."""
    secs = _tf_seconds(tf)
    return 1.0 + math.log10(max(secs, 60) / 60.0)   # 60s→1.0, 1h→2.78, 1d→3.16


def aggregate_timeframes(per_tf):
    """Combine per-TF trend + conviction into one honest directional call.

    Each timeframe votes by its trend (fired BUY/SELL weighted double), scaled by
    its setup score. The net decides direction; the spread of agreement + average
    conviction decide confidence. Direction is surfaced even on a 'lean' so the
    user always sees where price is biased — the confidence label tells the truth.
    """
    n = len(per_tf)
    if n == 0:
        return {"signal": "WAIT", "confidence": "LOW", "bias": "NEUTRAL",
                "alignment": "0/0", "aligned": 0, "n": 0, "buys": 0, "sells": 0,
                "strength": 0}

    fired_buy = sum(1 for p in per_tf if p["signal"] == "BUY")
    fired_sell = sum(1 for p in per_tf if p["signal"] == "SELL")
    bulls = bears = 0
    weighted = 0.0
    wtotal = 0.0
    for p in per_tf:
        d, w = _tf_dir(p)
        tw = _tf_weight(p["tf"])               # higher TFs dominate
        if d > 0:
            bulls += 1
        elif d < 0:
            bears += 1
        sc = (p["score"] or 0) / 100.0
        weighted += d * w * tw * (0.4 + sc)    # base × conviction × timeframe weight
        wtotal += w * tw * (0.4 + sc) if d != 0 else 0
    net = weighted / wtotal if wtotal else 0.0   # -1 .. 1
    aligned = max(bulls, bears)
    avg_score = sum(p["score"] or 0 for p in per_tf) / n

    if net > 0.12:
        bias, direction = "BULLISH", "BUY"
    elif net < -0.12:
        bias, direction = "BEARISH", "SELL"
    else:
        bias, direction = "NEUTRAL", None

    # Higher-timeframe trend filter — don't fight the major trend (Livermore/Murphy).
    # If the longest timeframe trends clearly against our direction, demote the call.
    htf = max(per_tf, key=lambda p: _tf_seconds(p["tf"]))
    htf_dir, _ = _tf_dir(htf)
    htf_conflict = (direction == "BUY" and htf_dir < 0 and (htf["score"] or 0) >= 50) or \
                   (direction == "SELL" and htf_dir > 0 and (htf["score"] or 0) >= 50)

    fired = fired_buy if direction == "BUY" else fired_sell if direction == "SELL" else 0
    strength = round(abs(net) * 100)
    frac = aligned / n if n else 0

    if direction is None or aligned < 2:
        sig, conf = "WAIT", "LOW"
    elif htf_conflict:
        sig, conf = direction, "LOW"           # against the higher-TF trend → lean only
    elif frac >= 0.66 and avg_score >= 58 and fired >= 2:
        sig, conf = direction, "HIGH"          # most TFs agree + multiple fired
    elif frac > 0.5 and (fired >= 1 or avg_score >= 50):
        sig, conf = direction, "MEDIUM"        # clear majority
    else:
        sig, conf = direction, "LOW"           # a lean — directional but weak/tied

    return {
        "signal": sig, "confidence": conf, "bias": bias,
        "alignment": f"{aligned}/{n}", "aligned": aligned, "n": n,
        "buys": bulls, "sells": bears, "strength": strength,
        "htf": htf["tf"], "htf_conflict": htf_conflict,
    }


# ---- report text ---------------------------------------------------------
def build_report(symbol, overall, strategy, per_tf, entry, pb=None):
    name, desc = strategy
    lines = [
        f"{symbol}: {overall['signal']} ({overall['confidence']} confidence, "
        f"{overall['bias'].lower()} bias).",
        f"Strategy — {name}: {desc}",
        f"Timeframe alignment: {overall['alignment']} agree on direction "
        f"({overall.get('buys', 0)} bullish / {overall.get('sells', 0)} bearish of {overall['n']} timeframes).",
    ]
    for p in per_tf:
        arrow = "▲" if p["signal"] == "BUY" else "▼" if p["signal"] == "SELL" else "•"
        lines.append(f"  {p['tf']}: {arrow} {p['signal']} {p['score']}% ({p['trend'].lower()})")
    if overall.get("htf_conflict"):
        lines.append(f"⚠ Against the higher-timeframe ({overall.get('htf')}) trend — "
                     f"don't fight the major trend; demoted to a lean (Livermore/Murphy).")

    if pb:
        loc = {"at_support": "at support", "at_resistance": "at resistance", "mid": "mid-range"}.get(pb["location"], pb["location"])
        patname = pb["pattern"]["name"] or "none"
        lines.append(
            f"Edge — price {loc}; candle pattern: {patname}. "
            f"Est. win-prob {int(pb['win_prob']*100)}% vs {int(pb['breakeven_winrate']*100)}% binary break-even "
            f"→ binary EV {pb['binary_ev']:+.2f}"
            + (f", spot EV {pb['spot_ev_r']:+.2f}R." if pb['spot_ev_r'] is not None else ".")
        )
        if pb.get("gate_note"):
            lines.append(f"⚠ {pb['gate_note']}")

    if entry and entry.get("direction") not in ("—", None):
        lines.append(
            f"Plan — {entry['direction']}: enter {entry['entry']}, "
            f"stop {entry['stop']}, target {entry['target']}, R:R {entry['risk_reward']}, "
            f"expiry {entry['expiry']}."
        )
    else:
        lines.append("Plan — no trade: wait for timeframes and indicators to align.")

    if pb and pb.get("principles"):
        lines.append("Principles applied:")
        for pr in pb["principles"]:
            lines.append(f"  • {pr['text']} ({pr['source']})")
    return "\n".join(lines)
