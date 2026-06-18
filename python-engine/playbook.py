"""
Trading playbook — a principles-driven rules layer.

Encodes the *methodologies* taught by the classic trading literature as explicit,
deterministic rules (the concepts are standard knowledge — no text is reproduced):

  • Trend is your friend; trade the dominant move ........ Livermore, Murphy
  • Cut losses fast, let winners run — risk IS the edge .. Schwager, Livermore
  • Take only positive-expectancy bets (R-multiples) ..... Tharp
  • Any single trade is random; think in probabilities ... Douglas, Duke
  • Short-term results are noisy; distrust small samples . Taleb
  • Demand margin of safety; never buy into resistance ... Graham, Murphy
  • No setup = no trade; avoid revenge/overtrading ....... Steenbarger
  • Trends overextend then reverse; respect exhaustion ... Soros

The engine uses these to (1) pick a strategy from regime + S/R location + candle
pattern + multi-timeframe agreement, (2) estimate an honest, capped win-probability,
(3) gate the call on expectancy, and (4) explain itself citing the principle.
"""

PRINCIPLES = {
    "trend":        ("Trade with the dominant trend — the big money is in the major moves.", "Livermore · Murphy"),
    "cut_losses":   ("Cut losses fast and let winners run; risk control is the real edge.", "Schwager · Livermore"),
    "expectancy":   ("Only take positive-expectancy bets — win%·reward must beat loss%·risk.", "Tharp"),
    "probabilities":("Any one trade is random; trade the process, not the outcome.", "Douglas · Duke"),
    "randomness":   ("Short-term P&L is noisy — demand robust agreement, distrust small samples.", "Taleb"),
    "safety":       ("Demand room to target; never buy into resistance or sell into support.", "Graham · Murphy"),
    "discipline":   ("No clean setup = no trade. Avoid overtrading and revenge trades.", "Steenbarger"),
    "reflexivity":  ("Trends overextend then snap back; respect exhaustion at extremes.", "Soros"),
}

# Candlestick pattern → (directional bias, kind, base reliability 0..1)
_PATTERN = {
    "hammer":               (1, "reversal", 0.55),
    "shooting star":        (-1, "reversal", 0.55),
    "bullish engulfing":    (1, "reversal", 0.62),
    "bearish engulfing":    (-1, "reversal", 0.62),
    "three white soldiers": (1, "continuation", 0.60),
    "three black crows":    (-1, "continuation", 0.60),
    "strong bull":          (1, "continuation", 0.45),
    "strong bear":          (-1, "continuation", 0.45),
    "doji":                 (0, "indecision", 0.30),
}

BINARY_PAYOUT = 0.85   # typical binary-option payout; break-even win-rate ≈ 54%

# Empirical win-rate calibration produced by run_backtest.py (grounds win-prob in
# measured history instead of pure heuristics). Loaded best-effort at import.
import json as _json
import os as _os

_CALIB = {}
try:
    _cp = _os.path.join(_os.path.dirname(__file__), "calibration.json")
    if _os.path.exists(_cp):
        with open(_cp) as _f:
            _CALIB = _json.load(_f)
except Exception:
    _CALIB = {}


def _empirical_winprob(score):
    """Measured win-rate for this setup-score bucket (or pooled), if we have enough samples."""
    cal = _CALIB.get("calibration") or {}
    b = "0-40" if score < 40 else "40-55" if score < 55 else "55-70" if score < 70 else "70-100"
    v = cal.get(b)
    if v and v.get("n", 0) >= 30 and v.get("win_rate") is not None:
        return v["win_rate"] / 100.0
    pooled = (_CALIB.get("pooled") or {}).get("win_rate")
    return pooled / 100.0 if pooled else None


def pattern_meta(pattern):
    p = (pattern or "").strip().lower()
    bias, kind, rel = _PATTERN.get(p, (0, "none", 0.0))
    return {"name": p, "bias": bias, "kind": kind, "reliability": rel}


def price_location(price, support, resistance, atr):
    """Where price sits in its range: 'at_support' / 'at_resistance' / 'mid'."""
    if atr and atr > 0:
        near = 0.6 * atr
        if support is not None and abs(price - support) <= near:
            return "at_support"
        if resistance is not None and abs(price - resistance) <= near:
            return "at_resistance"
    # fractional position if both levels known
    if support is not None and resistance is not None and resistance > support:
        pos = (price - support) / (resistance - support)
        if pos <= 0.2:
            return "at_support"
        if pos >= 0.8:
            return "at_resistance"
    return "mid"


def select_playbook(direction, adx, location, pat, aligned, n):
    """Choose the strategy + cite the principles it rests on."""
    trending = adx == adx and adx is not None and adx >= 25
    cites = ["probabilities", "cut_losses", "expectancy"]

    if direction not in ("BUY", "SELL"):
        cites = ["discipline", "randomness"]
        return ("Stand aside", "No clean, aligned setup — the highest-probability action is no trade.", cites)

    want_up = direction == "BUY"
    # Reversal pattern at the favourable edge, against a weak/over-extended move
    rev_at_edge = (
        pat["kind"] == "reversal" and pat["bias"] == (1 if want_up else -1)
        and ((want_up and location == "at_support") or (not want_up and location == "at_resistance"))
    )
    if rev_at_edge and not trending:
        cites = ["safety", "reflexivity", "expectancy", "probabilities"]
        return ("Reversal at S/R",
                f"{pat['name'].title()} rejecting {'support' if want_up else 'resistance'} in a range — "
                f"fading the move with a tight stop beyond the level (margin of safety).", cites)

    if trending and ((want_up and location != "at_resistance") or (not want_up and location != "at_support")):
        cites = ["trend", "cut_losses", "expectancy", "probabilities"]
        return ("Trend-following",
                "Strong directional trend with room to target — trading with the trend, "
                "buying dips / selling rallies, riding the major move.", cites)

    if pat["kind"] == "continuation" and pat["bias"] == (1 if want_up else -1) and trending:
        cites = ["trend", "cut_losses", "probabilities"]
        return ("Momentum continuation",
                f"{pat['name'].title()} with the trend — pressing the move while momentum persists.", cites)

    # buying into resistance / selling into support → poor location, demote
    bad_loc = (want_up and location == "at_resistance") or (not want_up and location == "at_support")
    if bad_loc:
        cites = ["safety", "discipline", "randomness"]
        return ("Poor location — caution",
                "Signal points into the opposite barrier (buying near resistance / selling near support) — "
                "little room to target; margin of safety is thin.", cites)

    cites = ["probabilities", "expectancy", "randomness"]
    return ("Multi-factor confluence",
            "Several indicator categories agree across timeframes, without a single dominant regime.", cites)


def estimate_win_prob(direction, adx, location, pat, aligned, n, avg_score,
                      model_prob, playbook_name):
    """Honest, capped win-probability estimate. Capped per Taleb — never over-claim."""
    if direction not in ("BUY", "SELL"):
        return 0.50
    # Anchor to MEASURED win-rate for this setup-score bucket when available
    # (run_backtest.py → calibration.json); otherwise fall back to 0.50.
    base = _empirical_winprob(avg_score)
    p = base if base is not None else 0.50
    want_up = direction == "BUY"
    trending = adx == adx and adx is not None and adx >= 25

    # multi-timeframe agreement (the main lever)
    p += min(0.12, 0.03 * max(0, aligned - 1))
    if n and aligned / n >= 0.66:
        p += 0.03
    # conviction
    p += min(0.05, (avg_score - 50) / 500.0) if avg_score else 0
    # trend in our favour
    if trending and playbook_name in ("Trend-following", "Momentum continuation"):
        p += 0.05
    # pattern at the right location
    if pat["bias"] == (1 if want_up else -1):
        p += pat["reliability"] * 0.10
    # location quality (margin of safety)
    if (want_up and location == "at_support") or (not want_up and location == "at_resistance"):
        p += 0.03
    if (want_up and location == "at_resistance") or (not want_up and location == "at_support"):
        p -= 0.06
    # model concurrence
    if model_prob is not None:
        if (model_prob > 0.5) == want_up:
            p += 0.02
        else:
            p -= 0.02

    return round(max(0.35, min(0.70, p)), 3)   # humility cap


def apply(direction, confidence, adx, price, levels, atr, pattern,
          aligned, n, avg_score, risk_reward, model_prob):
    """Full principles pass → strategy, win-prob, expectancy gating, rationale."""
    sup = (levels or {}).get("support")
    res = (levels or {}).get("resistance")
    loc = price_location(price, sup, res, atr)
    pat = pattern_meta(pattern)
    name, desc, cite_keys = select_playbook(direction, adx, loc, pat, aligned, n)
    win_prob = estimate_win_prob(direction, adx, loc, pat, aligned, n, avg_score,
                                 model_prob, name)

    rr = risk_reward or 0
    # spot expectancy in R-multiples (Tharp), and binary EV at typical payout
    spot_ev_r = round(win_prob * rr - (1 - win_prob), 3) if rr else None
    binary_ev = round(win_prob * BINARY_PAYOUT - (1 - win_prob), 3)
    breakeven = round(1 / (1 + BINARY_PAYOUT), 3)   # ≈ 0.541

    # Expectancy gate: a confident BUY/SELL must clear break-even edge.
    gated_signal, gated_conf, gate_note = direction, confidence, None
    if direction in ("BUY", "SELL"):
        if win_prob <= breakeven and (spot_ev_r is None or spot_ev_r <= 0):
            gated_signal = direction            # keep the lean/direction
            gated_conf = "LOW"
            gate_note = (f"Edge below break-even (win~{int(win_prob*100)}% vs "
                         f"{int(breakeven*100)}% needed) — treat as a lean, not a trade (Tharp · Taleb).")
        elif loc in ("at_resistance", "at_support") and name == "Poor location — caution":
            gated_conf = "LOW" if confidence == "HIGH" else gated_conf
            gate_note = "Poor entry location — margin of safety thin (Graham)."

    principles = [{"text": PRINCIPLES[k][0], "source": PRINCIPLES[k][1]} for k in cite_keys]
    return {
        "strategy": {"name": name, "description": desc},
        "location": loc,
        "pattern": pat,
        "win_prob": win_prob,
        "spot_ev_r": spot_ev_r,
        "binary_ev": binary_ev,
        "breakeven_winrate": breakeven,
        "principles": principles,
        "gated_signal": gated_signal,
        "gated_confidence": gated_conf,
        "gate_note": gate_note,
    }
