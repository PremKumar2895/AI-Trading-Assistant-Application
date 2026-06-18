"""
Multi-indicator confluence / trend-confirmation engine.

Every indicator casts a weighted vote: +1 bullish, -1 bearish, 0 neutral. Votes are
grouped into categories (trend / momentum / volatility / volume / pattern). A signal
is only confirmed when the *categories agree* AND the weighted confluence clears a
threshold — i.e. "all even and good, then give the signal". Otherwise it returns a
WAIT with explicit feedback on what is missing.

Output is advisory only (no execution), with a transparent breakdown so the user can
see *why*. Consumes the OHLCV-derived indicators from `indicators.compute_all`.
"""
from indicators import compute_all, PATTERN_BIAS

CATEGORIES = ["trend", "momentum", "volatility", "volume", "pattern"]

_MODEL = None
_MODEL_LOADED = False


def _get_model():
    """Lazy-load the trained model once (None if not trained yet)."""
    global _MODEL, _MODEL_LOADED
    if not _MODEL_LOADED:
        _MODEL_LOADED = True
        try:
            from model import TradeModel
            _MODEL = TradeModel.load()
        except Exception as e:
            print(f"Model load skipped: {e}")
            _MODEL = None
    return _MODEL


def _vote(name, category, vote, weight, detail):
    return {
        "name": name,
        "category": category,
        "vote": int(vote),
        "weight": float(weight),
        "detail": detail,
    }


def _build_votes(ind):
    v = []
    c = ind["close"]

    # ---- TREND ----
    if ind["ema9"] == ind["ema9"]:  # not NaN
        if ind["ema9"] > ind["ema21"] > ind["ema50"]:
            v.append(_vote("EMA stack", "trend", 1, 1.4, "EMA 9>21>50 (up)"))
        elif ind["ema9"] < ind["ema21"] < ind["ema50"]:
            v.append(_vote("EMA stack", "trend", -1, 1.4, "EMA 9<21<50 (down)"))
        else:
            v.append(_vote("EMA stack", "trend", 0, 1.4, "EMAs mixed"))

    if ind["macd_hist"] == ind["macd_hist"]:
        mv = 1 if ind["macd"] > ind["macd_signal"] else -1
        v.append(_vote("MACD", "trend", mv, 1.2,
                       f"MACD {'>' if mv > 0 else '<'} signal"))

    adx = ind["adx"]
    if adx == adx:
        if adx >= 25:
            dirn = 1 if ind["plus_di"] > ind["minus_di"] else -1
            v.append(_vote("ADX/DI", "trend", dirn, 1.3,
                           f"ADX {adx:.0f} strong, {'+DI' if dirn>0 else '-DI'} leads"))
        else:
            v.append(_vote("ADX/DI", "trend", 0, 1.3, f"ADX {adx:.0f} weak/range"))

    v.append(_vote("Supertrend", "trend", int(ind["supertrend_dir"]), 1.3,
                   "up" if ind["supertrend_dir"] > 0 else "down"))

    v.append(_vote("Parabolic SAR", "trend", 1 if ind["psar_below"] else -1, 0.9,
                   "SAR below price" if ind["psar_below"] else "SAR above price"))

    if ind["cloud_top"] == ind["cloud_top"]:
        if c > ind["cloud_top"]:
            v.append(_vote("Ichimoku cloud", "trend", 1, 1.1, "price above cloud"))
        elif c < ind["cloud_bot"]:
            v.append(_vote("Ichimoku cloud", "trend", -1, 1.1, "price below cloud"))
        else:
            v.append(_vote("Ichimoku cloud", "trend", 0, 1.1, "price in cloud"))

    # ---- MOMENTUM ----
    # Trend-aware: in a confirmed trend (ADX>=25) oscillator extremes mean
    # *continuation*, so we don't fade them. In a range we mean-revert.
    adx = ind["adx"]
    strong_trend = adx == adx and adx >= 25

    rsi = ind["rsi"]
    if rsi == rsi:
        if strong_trend:
            rv = 1 if rsi > 50 else -1
            v.append(_vote("RSI", "momentum", rv, 1.0, f"RSI {rsi:.0f} ({'up' if rv>0 else 'down'} momentum)"))
        elif rsi >= 70:
            v.append(_vote("RSI", "momentum", -1, 1.1, f"RSI {rsi:.0f} overbought (range)"))
        elif rsi <= 30:
            v.append(_vote("RSI", "momentum", 1, 1.1, f"RSI {rsi:.0f} oversold (range)"))
        elif rsi > 55:
            v.append(_vote("RSI", "momentum", 1, 0.9, f"RSI {rsi:.0f} bullish"))
        elif rsi < 45:
            v.append(_vote("RSI", "momentum", -1, 0.9, f"RSI {rsi:.0f} bearish"))
        else:
            v.append(_vote("RSI", "momentum", 0, 0.9, f"RSI {rsi:.0f} neutral"))

    k, d = ind["stoch_k"], ind["stoch_d"]
    if k == k:
        if strong_trend:
            sv = 1 if k > d else -1
        else:
            sv = 1 if k < 20 else -1 if k > 80 else (1 if k > d else -1)
        v.append(_vote("Stochastic", "momentum", sv, 0.9, f"%K {k:.0f}/%D {d:.0f}"))

    srsi = ind["stoch_rsi"]
    if srsi == srsi:
        if strong_trend:
            sv = 1 if srsi > 50 else -1
        else:
            sv = 1 if srsi < 20 else -1 if srsi > 80 else (1 if srsi > 50 else -1)
        v.append(_vote("Stoch RSI", "momentum", sv, 0.7, f"{srsi:.0f}"))

    cci = ind["cci"]
    if cci == cci:
        cv = 1 if cci > 100 else -1 if cci < -100 else (1 if cci > 0 else -1)
        v.append(_vote("CCI", "momentum", cv, 0.8, f"CCI {cci:.0f}"))

    wr = ind["williams_r"]
    if wr == wr:
        if strong_trend:
            wv = 1 if wr > -50 else -1
        else:
            wv = 1 if wr < -80 else -1 if wr > -20 else (1 if wr > -50 else -1)
        v.append(_vote("Williams %R", "momentum", wv, 0.6, f"{wr:.0f}"))

    roc = ind["roc"]
    if roc == roc:
        v.append(_vote("ROC", "momentum", 1 if roc > 0 else -1, 0.7, f"ROC {roc:+.2f}%"))

    # ---- VOLUME ----
    mfi = ind["mfi"]
    if mfi == mfi:
        mv = 1 if mfi < 20 else -1 if mfi > 80 else (1 if mfi > 55 else -1 if mfi < 45 else 0)
        v.append(_vote("MFI", "volume", mv, 0.9, f"MFI {mfi:.0f}"))

    ov = ind["obv_slope"]
    v.append(_vote("OBV slope", "volume", 1 if ov > 0 else -1 if ov < 0 else 0, 0.8,
                   "rising" if ov > 0 else "falling" if ov < 0 else "flat"))

    if ind["vwap"] == ind["vwap"]:
        v.append(_vote("VWAP", "volume", 1 if c > ind["vwap"] else -1, 0.7,
                       "above VWAP" if c > ind["vwap"] else "below VWAP"))

    # ---- VOLATILITY ----
    pb = ind["bb_pb"]
    if pb == pb:
        if pb >= 1.0:
            v.append(_vote("Bollinger", "volatility", -1, 0.9, "at/above upper band"))
        elif pb <= 0.0:
            v.append(_vote("Bollinger", "volatility", 1, 0.9, "at/below lower band"))
        else:
            v.append(_vote("Bollinger", "volatility", 0, 0.5, f"%B {pb:.2f} mid-band"))

    if ind["kc_upper"] == ind["kc_upper"]:
        if c > ind["kc_upper"]:
            v.append(_vote("Keltner", "volatility", 1, 0.6, "breakout above"))
        elif c < ind["kc_lower"]:
            v.append(_vote("Keltner", "volatility", -1, 0.6, "breakdown below"))
        else:
            v.append(_vote("Keltner", "volatility", 0, 0.4, "inside channel"))

    if ind["dc_upper"] == ind["dc_upper"]:
        if c >= ind["dc_upper"]:
            v.append(_vote("Donchian", "volatility", 1, 0.7, "new high breakout"))
        elif c <= ind["dc_lower"]:
            v.append(_vote("Donchian", "volatility", -1, 0.7, "new low breakdown"))
        else:
            v.append(_vote("Donchian", "volatility", 0, 0.4, "mid-range"))

    # ---- PATTERN ----
    pat = ind["pattern"]
    if pat:
        bias = PATTERN_BIAS.get(pat, 0)
        v.append(_vote("Candle pattern", "pattern", bias, 1.2, pat.replace("_", " ")))

    return v


def _aggregate(votes):
    cat_net = {cat: 0.0 for cat in CATEGORIES}
    cat_weight = {cat: 0.0 for cat in CATEGORIES}
    bull = bear = 0.0
    for vt in votes:
        w = vt["weight"]
        cat_net[vt["category"]] += vt["vote"] * w
        cat_weight[vt["category"]] += w
        if vt["vote"] > 0:
            bull += w
        elif vt["vote"] < 0:
            bear += w
    return cat_net, cat_weight, bull, bear


def decide(df, context=None, mtf_trend=None, min_conf=62, min_categories=3, use_model=True):
    """Return the unified advisory result from full-indicator confluence.

    `use_model=False` skips the (info-only) ML overlay — used by the backtester so
    it doesn't recompute the feature matrix on every bar (O(n²)).
    """
    if df is None or len(df) < 5:
        return _wait("Building candle history…", context)

    ind = compute_all(df)
    votes = _build_votes(ind)
    if not votes:
        return _wait("Indicators warming up…", context, ind)

    cat_net, cat_weight, bull, bear = _aggregate(votes)
    total = bull + bear

    # Optional external multi-timeframe bias as one extra trend vote.
    if mtf_trend in ("BULLISH", "BEARISH"):
        mtf_v = 1.5 if mtf_trend == "BULLISH" else -1.5
        cat_net["trend"] += mtf_v
        cat_weight["trend"] += 1.5
        bull += max(mtf_v, 0)
        bear += max(-mtf_v, 0)
        total = bull + bear
        votes.append(_vote("Multi-timeframe", "trend", 1 if mtf_v > 0 else -1, 1.5,
                           f"{mtf_trend.lower()} bias"))

    net = bull - bear
    direction = "BUY" if net > 0 else "SELL" if net < 0 else "WAIT"

    # Conviction = how lopsided the weighted vote is, direction-agnostic
    # (0 = perfectly split, 100 = unanimous). Used for thresholds & setup score.
    conf_pct = int(round(100 * abs(net) / total)) if total else 0
    conf_pct = max(0, min(100, conf_pct))

    # Category alignment: how many categories agree with the net direction.
    agree, disagree = [], []
    for cat in CATEGORIES:
        cn = cat_net[cat]
        if cat_weight[cat] == 0 or cn == 0:
            continue
        if (cn > 0) == (net > 0):
            agree.append(cat)
        else:
            disagree.append(cat)

    trend = "BULLISH" if net > 0 else "BEARISH" if net < 0 else "NEUTRAL"
    aligned = len(agree)
    confirmed = (
        direction in ("BUY", "SELL")
        and conf_pct >= min_conf
        and aligned >= min_categories
        and not (disagree and "trend" in disagree)  # never fight the trend bucket
    )

    # RSI hard guard — only in a RANGE (no ADX trend). In a strong trend, an
    # overbought RSI is continuation, so we don't block it here.
    rsi = ind.get("rsi")
    adx_v = ind.get("adx")
    ranging = not (adx_v == adx_v and adx_v >= 25)
    if confirmed and ranging and rsi == rsi:
        if direction == "BUY" and rsi >= 78:
            confirmed = False
        elif direction == "SELL" and rsi <= 22:
            confirmed = False

    factors = [f"{vt['name']}: {vt['detail']}"
               for vt in votes
               if vt["vote"] != 0 and (vt["vote"] > 0) == (net > 0)]
    against = [f"{vt['name']}: {vt['detail']}"
              for vt in votes
              if vt["vote"] != 0 and (vt["vote"] > 0) != (net > 0)]

    if confirmed:
        signal = direction
        confidence = "HIGH" if (conf_pct >= 78 and aligned >= 4) else "MEDIUM"
        reason = (
            f"{direction} confirmed — {aligned}/{len(CATEGORIES)} categories agree, "
            f"confluence {conf_pct}%. Top: " + "; ".join(factors[:3])
        )
        suggestion = _suggestion(direction, ind, conf_pct, context)
    else:
        signal = "WAIT"
        confidence = "LOW"
        reason = _why_wait(direction, conf_pct, aligned, disagree, min_conf, min_categories)
        suggestion = (
            f"Lean {trend.lower()} ({conf_pct}%) but not confirmed. "
            f"Need {min_categories}+ categories aligned and ≥{min_conf}% confluence."
        )

    # ---- learned-model overlay ----
    # The model only *elevates* a signal when it earned eligibility (positive EV
    # out-of-sample). Otherwise it is shown for transparency but cannot change the call.
    model_prob, model_eligible, model_note = _model_overlay(df) if use_model else (None, False, None)
    if model_prob is not None and model_eligible and signal in ("BUY", "SELL"):
        agrees = (model_prob > 0.5) == (signal == "BUY")
        edge = abs(model_prob - 0.5)
        if not agrees and edge > 0.12:
            signal, confidence = "WAIT", "LOW"
            reason = f"Model disagrees (P_up={model_prob:.2f}) — stand aside"
        elif agrees and edge > 0.12:
            confidence = "HIGH"
            reason += f" | model agrees P_up={model_prob:.2f}"

    # ---- support / resistance for display ----
    levels = _sr_levels(df, ind.get("atr"))

    return {
        "signal": signal,
        "confidence": confidence,
        "reason": reason,
        "suggestion": suggestion,
        "trend": trend,
        "setup_score": conf_pct,
        "confluence": factors[:6],
        "against": against[:4],
        "categories": {cat: round(cat_net[cat], 2) for cat in CATEGORIES},
        "categories_agree": agree,
        "pattern": (ind.get("pattern") or "").replace("_", " "),
        "indicators": _ui_breakdown(votes),
        "model_prob": model_prob,
        "model_eligible": model_eligible,
        "model_note": model_note,
        "levels": levels,
        "debug_info": {
            "bull": round(bull, 2), "bear": round(bear, 2),
            "net": round(net, 2), "aligned": aligned,
            "rsi": ind.get("rsi"), "adx": ind.get("adx"),
            "atr": ind.get("atr"), "n_candles": ind.get("n"),
        },
        "context": context,
    }


def _model_overlay(df):
    """Return (prob_up, eligible, note) from the learned model, or (None, False, None)."""
    m = _get_model()
    if m is None:
        return None, False, None
    try:
        from features import latest_row
        row = latest_row(df)
        if row is None:
            return None, m.eligible, None
        p = float(m.proba_up(row)[0])
        note = "calibrated model (active)" if m.eligible else "model: info only (not EV-eligible)"
        return round(p, 3), bool(m.eligible), note
    except Exception as e:
        print(f"Model overlay error: {e}")
        return None, False, None


def _sr_levels(df, atr_val):
    try:
        from support_resistance import nearest_levels
        lv = nearest_levels(df, atr_val or 0.0)
        return {
            "support": round(lv["support"], 5) if lv["support"] is not None else None,
            "resistance": round(lv["resistance"], 5) if lv["resistance"] is not None else None,
        }
    except Exception:
        return {"support": None, "resistance": None}


def _ui_breakdown(votes):
    """Compact list for the UI indicator panel."""
    return [
        {"name": vt["name"], "category": vt["category"],
         "vote": vt["vote"], "detail": vt["detail"]}
        for vt in votes
    ]


def _suggestion(direction, ind, conf_pct, context):
    arrow = "UP / CALL" if direction == "BUY" else "DOWN / PUT"
    rsi = ind.get("rsi")
    atr = ind.get("atr")
    extra = ""
    if context and context.get("platform") == "Binomo":
        extra = f" Press {('UP' if direction=='BUY' else 'DOWN')} on next candle open."
    return (
        f"Suggested: {arrow} ({conf_pct}% confluence). "
        f"RSI {rsi:.0f}, volatility {('high' if atr and atr>0 else 'n/a')}.{extra}"
    )


def _why_wait(direction, conf_pct, aligned, disagree, min_conf, min_categories):
    if direction == "WAIT":
        return "Indicators evenly split — no directional edge. Hold."
    bits = []
    if conf_pct < min_conf:
        bits.append(f"confluence {conf_pct}% < {min_conf}%")
    if aligned < min_categories:
        bits.append(f"only {aligned}/{min_categories} categories aligned")
    if disagree:
        bits.append("conflict in " + ", ".join(disagree))
    return f"Leaning {direction.lower()} but waiting: " + "; ".join(bits) + "."


def _wait(reason, context, ind=None):
    return {
        "signal": "WAIT",
        "confidence": "LOW",
        "reason": reason,
        "suggestion": "Collecting more candles before analysing.",
        "trend": "NEUTRAL",
        "setup_score": 0,
        "confluence": [],
        "against": [],
        "categories": {},
        "categories_agree": [],
        "indicators": [],
        "debug_info": {"n_candles": ind.get("n") if ind else 0},
        "context": context,
    }
