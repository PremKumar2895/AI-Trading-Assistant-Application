# AI Trading Assistant — Architecture & Roadmap

> **Status:** Proposed design (v0.1). No application code changes implied by this
> document — it is the plan we agreed to review *before* building.
>
> **Decisions locked in (from planning session 2026-06-08):**
> 1. Deliverable for this round = **this document** (architecture + roadmap), not app code.
> 2. Scope = **universal**: must work across Binomo synthetic indices, real crypto,
>    forex, stocks, and "anything on screen". This forces a **hybrid data layer**
>    (real market APIs where they exist; calibrated screen-vision where they don't).
> 3. Risk posture = **Advisory + Alerts only**. The app shows signals and fires
>    desktop/sound alerts. **It never places or sizes real orders.** The user always
>    clicks the trade themselves.

---

## 0. Honest framing (the non-negotiable preamble)

This shapes every design choice, so it lives at the top.

- **Binary options have negative baseline expectancy.** With an 70–90% payout, the
  break-even win rate is **~53–59%**. The product must therefore *measure and display*
  its real hit rate, not advertise an invented "confidence %". Calibration is a
  first-class feature, not a nicety.
- **Synthetic indices (Crypto IDX, Altcoin IDX) have no underlying market and no public
  data.** They are broker-generated RNG-with-drift. We can only learn from *our own
  logged outcomes* on them — never from an external feed. Manage expectations
  accordingly in the UI.
- **Pixels are a lossy, last-resort data source.** Where a real feed exists (crypto via
  exchange APIs, forex/stocks via data vendors), we use it. Vision is the fallback that
  makes the app *universal*, not the primary path.
- **No claim of profit.** The system's job is to surface statistically-characterised
  setups and track them honestly. That is the product.

---

## 1. Target architecture (high level)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  DESKTOP (Electron)                                                        │
│                                                                            │
│   capture.js ──frames──┐         ┌── alerts (desktop notif + sound)        │
│   preload bridge ◄─────┤  UI  ◄──┤── signal / win-rate / history view      │
│   (contextIsolation)   └─►IPC────┘                                         │
└───────────────┬──────────────────────────────────────────▲───────────────┘
                │ WebSocket (frames out, signals in)         │
┌───────────────▼────────────────────────────────────────── ┴──────────────┐
│  PYTHON ENGINE (FastAPI)                                                    │
│                                                                            │
│  ┌────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   │
│  │ providers/ │──►│  features/   │──►│   model/     │──►│   policy/    │   │
│  │ data layer │   │ indicators + │   │ inference +  │   │ signal gate +│   │
│  │ (hybrid)   │   │ feature eng. │   │ calibration  │   │ trade plan   │   │
│  └─────┬──────┘   └──────────────┘   └──────────────┘   └──────┬───────┘   │
│        │                                                       │           │
│        │              ┌────────────────────────────┐          │           │
│        └─────────────►│        tracking/           │◄─────────┘           │
│                       │  signal log + outcome label │                      │
│                       │  (DuckDB/SQLite)            │                      │
│                       └─────────────┬───────────────┘                      │
│                                     │ offline                              │
│                       ┌─────────────▼───────────────┐                      │
│                       │  training/ + backtest/      │  (walk-forward CV,   │
│                       │  produces calibrated model  │   isotonic calib.)   │
│                       └─────────────────────────────┘                      │
└────────────────────────────────────────────────────────────────────────── ┘
```

The key structural change vs. today: a clean **left-to-right pipeline** with a
**closed feedback loop** through `tracking/`. Today the pipeline exists but the loop
does not — nothing records what happened after a signal, so nothing can learn.

---

## 2. Module breakdown (proposed Python package layout)

```
python-engine/
  app.py                 # FastAPI WS server — orchestration only, thin
  config.py              # pydantic Settings: thresholds, per-asset params, FPS
  providers/
    base.py              # DataProvider protocol: get_ohlcv(symbol, tf, n) -> DataFrame
    vision_provider.py   # screen → calibrated OHLC  (replaces screen_analyzer guts)
    crypto_api.py        # real crypto OHLCV (Crypto.com MCP / ccxt)
    forex_api.py         # forex OHLCV (vendor adapter)
    stocks_api.py        # equities OHLCV (vendor adapter)
    router.py            # picks provider by symbol/platform; vision is fallback
  vision/
    calibrate.py         # OCR y-axis price labels → price-per-pixel mapping
    candles.py           # true OHLC extraction per candle (body + wicks)
    chart_locate.py      # find chart region, axes (replaces fixed-fraction crops)
  features/
    indicators.py        # EMA/RSI/MACD/ATR/Bollinger/ADX via pandas-ta
    engineer.py          # assemble model feature vector from OHLCV + context
  model/
    baseline.py          # current rule engine, kept as fallback + label source
    predictor.py         # LightGBM inference + isotonic calibration wrapper
    artifacts/           # versioned model files + calibration maps
  policy/
    gate.py              # confluence/threshold gate (data-driven, not hand-tuned)
    trade_plan.py        # direction, expiry, advisory text (NO execution)
  tracking/
    store.py             # DuckDB/SQLite schema + writes
    outcome.py           # after-expiry result capture & labelling
  training/
    dataset.py           # build labelled dataset from tracking store
    train.py             # walk-forward CV training + calibration fit
  backtest/
    engine.py            # replay logged/historical data, compute hit rate, EV
  windows/
    window_manager.py    # active-window/platform detection (kept, de-duped)
  tests/                 # real pytest suite (replaces debug_*.py / test_*.py)
```

What gets retired: `binomo_analyzer.py` (legacy shim), `debug_colors.py`,
`debug_titles.py`, `debug_windows.py`, `test_detection.py`, `test_is_our_app.py`
(scratch scripts → fold useful bits into `tests/`).

---

## 3. The hybrid data layer (this is what makes it "universal")

A single `DataProvider` interface, with a router that chooses the source:

| Symbol / platform | Provider | Quality |
|---|---|---|
| BTC/USD, ETH/USD, real crypto | `crypto_api` (Crypto.com MCP `get_market_candles`, or `ccxt`) | **Clean OHLCV** |
| EUR/USD, GBP/USD, forex | `forex_api` (vendor adapter) | Clean OHLCV (vendor-dependent) |
| AAPL, TSLA, equities | `stocks_api` (vendor adapter) | Clean OHLCV (intraday may need paid feed) |
| Crypto IDX / Altcoin IDX / unknown | `vision_provider` | **Calibrated pixels** (fallback) |

`router.py` resolves the active symbol/platform (from window title + OCR), then asks
the best available provider for OHLCV. **Everything downstream (features, model,
policy) consumes a normalised OHLCV DataFrame** and no longer cares whether it came
from an API or the screen. This is the decoupling the current code lacks.

### 3.1 Vision provider upgrade (for the no-API case)

Today: 52 fixed columns → colored extent only. Proposed:

1. `chart_locate` finds the plot area and the price axis (not hard-coded fractions).
2. `calibrate` OCRs ≥2 y-axis price labels → linear **price-per-pixel** map.
3. `candles` extracts **true O/H/L/C + wicks** per candle and converts pixel-y to
   real price via the calibration map.

Result: even screen-only instruments yield *numeric* OHLC, so the *same* real
indicators run on them. (Accuracy is still bounded by OCR/zoom, and we say so.)

---

## 4. Features & model (the "self-learning" done correctly)

### 4.1 Features (`features/`)
Real indicators on real OHLCV: EMA(9/21/50), RSI(14), MACD, ATR(14) for volatility &
risk sizing, Bollinger width, ADX (trend strength), candle-pattern flags, plus context
(timeframe, session/time-of-day, payout%). ATR replaces the current flat 0.5% risk.

### 4.2 Model (`model/`)
- **Baseline** = today's rule engine. It keeps running and **also serves as a label/feature
  source** while data accumulates. Never delete it — it's the cold-start brain.
- **Learner** = LightGBM (gradient-boosted trees) trained on *logged outcomes*.
  Tabular, fast, interpretable (feature importances), strong on this data shape.
- **Calibration** = isotonic/Platt on a held-out time slice so a displayed "70%"
  equals an empirical ~70% hit rate. **This is the headline feature.**

### 4.3 Validation (`training/`, `backtest/`) — the part most hobby projects get wrong
- **Walk-forward / time-series split only.** Never random k-fold — it leaks the future
  into the past and produces beautiful, fake accuracy.
- **Backtest reports EV, not just win rate**, against the actual payout (e.g. "54%
  hit, 80% payout ⇒ negative EV ⇒ do not trust"). The harness can *veto* a model.
- **Paper-first:** a model is advisory-eligible only after it clears a configurable
  out-of-sample bar.

---

## 5. The feedback loop (`tracking/`) — the missing keystone

This is Phase 1 because nothing else can "learn" without it.

**Signal table (write at signal time):**
`id, ts, platform, symbol, timeframe, direction, expiry_ts, entry_price,
features_json, model_version, predicted_prob, gate_passed`

**Outcome table (write after expiry):**
`signal_id, settle_ts, settle_price, result(win/loss/flat), latency_ms`

Outcome capture: after `expiry_ts`, the engine re-reads price (same provider) and
labels the signal. Over days/weeks this becomes the training set *and* powers the live
**"last N signals: X% hit / break-even needs Y%"** widget — honesty as a feature.

---

## 6. Advisory + Alerts subsystem (no execution, by decision)

- **Channels:** in-overlay banner (exists), OS desktop notification, sound cue,
  optional later: Telegram/push.
- **Trigger:** only when `gate_passed` AND calibrated prob ≥ threshold AND not a
  duplicate of the last alert (debounce).
- **Hard boundary:** there is **no order-execution module** in this design. `trade_plan`
  emits *advice* ("Press UP, expiry 14:32") and an alert. The user acts manually.
  (If automation is ever revisited, it would be a separate, guardrailed project with
  its own review — explicitly out of scope here.)

---

## 7. Desktop / security fixes

Current `main.js` uses `nodeIntegration:true`, `contextIsolation:false`,
`webSecurity:false` — convenient for an MVP, risky for a shipped app.
Proposed: **preload script + `contextIsolation:true`**, exposing a minimal typed IPC
bridge (`window.api.startScan()`, `onSignal()`, …) instead of raw `require('electron')`
in the renderer. Plus: configurable capture FPS/region (today hard-coded 280ms and
1920×1080), and a settings panel.

---

## 8. Tech stack additions

| Area | Add | Why |
|---|---|---|
| Data | `pandas`, `duckdb` (or sqlite) | Normalised OHLCV + the tracking store |
| Indicators | `pandas-ta` (or TA-Lib) | Real EMA/RSI/MACD/ATR/ADX |
| Crypto feed | Crypto.com MCP / `ccxt` | Clean real OHLCV |
| ML | `scikit-learn`, `lightgbm` | Calibrated learner + isotonic calibration |
| Config | `pydantic-settings` | Typed thresholds / per-asset params |
| Tests | `pytest` | Replace scratch debug scripts |
| Desktop | preload + contextIsolation | Security |

---

## 9. Phased roadmap

| Phase | Goal | Deliverables | Depends on |
|---|---|---|---|
| **1. Foundation** | Make the system *measurable* | `tracking/` store + outcome capture; live win-rate widget; package restructure; retire shims/scratch | — |
| **2. Better data** | Raise the accuracy ceiling | Hybrid `providers/` + router; vision calibration (price-per-pixel, true OHLC); real `pandas-ta` indicators | 1 |
| **3. Self-learning** | Calibrated, validated model | `features/` pipeline; LightGBM + isotonic calibration; walk-forward training; backtest harness with EV veto | 1, 2 |
| **4. Harden & UX** | Shippable | Electron security (preload/contextIsolation); settings; signal-history view; ATR risk; alerts subsystem; packaging | 1–3 |

Recommended order is 1 → 2 → 3 → 4. Phase 1 alone already changes the product from
"trust me" to "here's my measured track record".

---

## 10. Known limitations & risks (state these in-app)

- Synthetic indices: learnable only from own outcomes; inherently low edge.
- Vision accuracy bounded by zoom/theme/OCR; calibration mitigates, doesn't eliminate.
- Binary-options payout math means a "good" model can still be break-even — surfaced by
  the EV backtest, not hidden.
- Advisory only: the app is a decision-support tool, not a trading bot, by design.

---

## 11. Open decisions for next session

1. **Datastore:** DuckDB (great for analytics/backtests) vs SQLite (simpler, ubiquitous)?
2. **Forex/stocks data vendor:** which API (some intraday feeds are paid)? Affects
   how much of "universal" is real-data vs vision on day one.
3. **Outcome capture cadence:** keep the engine polling price after expiry, or capture
   from the next frames? (Affects accuracy of the learning labels.)
4. **First instrument to instrument-test the new pipeline** end-to-end (suggest: real
   crypto via the already-connected Crypto.com MCP — cleanest data to validate plumbing).
```
