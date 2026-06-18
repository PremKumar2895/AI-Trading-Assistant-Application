import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import ChartCanvas from './ChartCanvas';
const { ipcRenderer } = window.require('electron');

const API = 'http://127.0.0.1:8000';
const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '1d'];

function fmtSignal(s) {
    if (s === 'BUY') return '▲ BUY';
    if (s === 'SELL') return '▼ SELL';
    return s === 'WAIT' ? 'WAIT' : s;
}

function fmtAge(min) {
    if (min == null) return '—';
    if (min < 60) return `${Math.round(min)} min`;
    if (min < 1440) return `${(min / 60).toFixed(1)} h`;
    return `${(min / 1440).toFixed(1)} d`;
}

export default function App() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState([]);
    const [showResults, setShowResults] = useState(false);
    const [asset, setAsset] = useState(null);          // {symbol, name, type}
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [activeTf, setActiveTf] = useState('1m');
    const [tfs, setTfs] = useState(TIMEFRAMES);
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [engineUp, setEngineUp] = useState(false);
    // Backtest, scanner, alerts, position sizing
    const [backtest, setBacktest] = useState(null);
    const [btLoading, setBtLoading] = useState(false);
    const [scanOpen, setScanOpen] = useState(false);
    const [scanRows, setScanRows] = useState([]);
    const [scanning, setScanning] = useState(false);
    const [alertsOn, setAlertsOn] = useState(true);
    const [account, setAccount] = useState(() => Number(localStorage.getItem('acct')) || 1000);
    const [riskPct, setRiskPct] = useState(() => Number(localStorage.getItem('risk')) || 1);

    const searchTimer = useRef(null);
    const refreshTimer = useRef(null);
    const boxRef = useRef(null);
    const lastAlertKey = useRef(null);
    const audioRef = useRef(null);

    useEffect(() => { localStorage.setItem('acct', account); }, [account]);
    useEffect(() => { localStorage.setItem('risk', riskPct); }, [riskPct]);
    useEffect(() => {
        try { if (window.Notification && Notification.permission === 'default') Notification.requestPermission(); } catch {}
    }, []);

    // --- engine health poll ---
    useEffect(() => {
        let alive = true;
        const ping = async () => {
            try {
                const r = await fetch(`${API}/health`, { cache: 'no-store' });
                if (alive) setEngineUp(r.ok);
            } catch { if (alive) setEngineUp(false); }
        };
        ping();
        const id = setInterval(ping, 4000);
        return () => { alive = false; clearInterval(id); };
    }, []);

    // --- search (debounced) ---
    const doSearch = useCallback((q) => {
        clearTimeout(searchTimer.current);
        searchTimer.current = setTimeout(async () => {
            try {
                const r = await fetch(`${API}/search?q=${encodeURIComponent(q)}`);
                const j = await r.json();
                setResults(j.results || []);
                setShowResults(true);
            } catch { setResults([]); }
        }, 220);
    }, []);

    useEffect(() => { doSearch(query); }, [query, doSearch]);

    // close result dropdown on outside click
    useEffect(() => {
        const onClick = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setShowResults(false); };
        document.addEventListener('mousedown', onClick);
        return () => document.removeEventListener('mousedown', onClick);
    }, []);

    const runAnalyze = useCallback(async (sym, silent = false) => {
        if (!sym) return;
        if (!silent) setLoading(true);
        setError('');
        try {
            const r = await fetch(`${API}/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: sym, timeframes: tfs }),
            });
            const j = await r.json();
            if (j.signal === 'INFO' || j.error) {
                setError(j.reason || 'No data for this asset.');
                setReport(null);
            } else {
                setReport(j);
                setActiveTf((prev) => (j.timeframes.some((t) => t.tf === prev) ? prev : j.timeframes[0]?.tf));
            }
        } catch (e) {
            setError('Engine offline — is the Python engine running on port 8000?');
        } finally {
            setLoading(false);
        }
    }, [tfs]);

    const selectAsset = (a) => {
        setAsset(a);
        setQuery(a.symbol);
        setShowResults(false);
        setReport(null);
        setBacktest(null);
        runAnalyze(a.symbol);
    };

    const runBacktest = async () => {
        if (!asset) return;
        setBtLoading(true); setBacktest(null);
        try {
            const r = await fetch(`${API}/backtest`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ symbol: asset.symbol, timeframes: ['5m', '15m', '1h', '1d'] }),
            });
            setBacktest(await r.json());
        } catch { setBacktest({ error: 'Backtest failed — engine offline?' }); }
        finally { setBtLoading(false); }
    };

    const runScan = useCallback(async () => {
        setScanning(true);
        try {
            const r = await fetch(`${API}/scan`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
            });
            const j = await r.json();
            setScanRows(j.results || []);
        } catch { setScanRows([]); }
        finally { setScanning(false); }
    }, []);

    useEffect(() => { if (scanOpen) runScan(); }, [scanOpen, runScan]);

    // --- alerts: notify on a NEW actionable, live, confident signal ---
    useEffect(() => {
        if (!alertsOn || !report?.overall) return;
        const o = report.overall;
        if (o.stale || !['BUY', 'SELL'].includes(o.signal) || !['MEDIUM', 'HIGH'].includes(o.confidence)) return;
        const key = `${report.symbol}|${o.signal}|${report.entry?.expiry || ''}`;
        if (key === lastAlertKey.current) return;
        lastAlertKey.current = key;
        try {
            if (window.Notification && Notification.permission === 'granted')
                new Notification(`${o.signal} ${report.symbol}`, { body: `${report.strategy?.name} · win ${Math.round((o.win_prob || 0) * 100)}% · ${report.entry?.direction || ''}` });
        } catch {}
        try {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            const ctx = audioRef.current || new Ctx(); audioRef.current = ctx;
            const osc = ctx.createOscillator(), g = ctx.createGain();
            osc.connect(g); g.connect(ctx.destination); osc.type = 'sine';
            osc.frequency.value = o.signal === 'BUY' ? 880 : 440;
            const t = ctx.currentTime; g.gain.setValueAtTime(0.0001, t);
            g.gain.exponentialRampToValueAtTime(0.25, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
            osc.start(t); osc.stop(t + 0.36);
        } catch {}
    }, [report, alertsOn]);

    // position size from account + risk% and the stop distance
    const positionSize = () => {
        const e = report?.entry;
        if (!e || e.entry == null || e.stop == null) return null;
        const riskAmt = account * (riskPct / 100);
        const perUnit = Math.abs(Number(e.entry) - Number(e.stop));
        if (!perUnit) return null;
        const units = riskAmt / perUnit;
        return { riskAmt: riskAmt.toFixed(2), units: units >= 1 ? units.toFixed(2) : units.toFixed(4) };
    };

    // --- auto refresh ---
    useEffect(() => {
        clearInterval(refreshTimer.current);
        if (autoRefresh && asset) {
            refreshTimer.current = setInterval(() => runAnalyze(asset.symbol, true), 15000);
        }
        return () => clearInterval(refreshTimer.current);
    }, [autoRefresh, asset, runAnalyze]);

    const toggleTf = (tf) => {
        setTfs((prev) => {
            const next = prev.includes(tf) ? prev.filter((t) => t !== tf) : [...prev, tf];
            const ordered = TIMEFRAMES.filter((t) => next.includes(t));
            return ordered.length ? ordered : prev;
        });
    };
    useEffect(() => { if (asset) runAnalyze(asset.symbol); }, [tfs]); // re-analyze on TF change

    const overall = report?.overall;
    const entry = report?.entry;
    const activeTfData = report?.timeframes?.find((t) => t.tf === activeTf) || report?.timeframes?.[0];
    const sigClass = (overall?.signal || 'wait').toLowerCase();

    return (
        <div className="v2-app">
            {/* ---- Title bar ---- */}
            <div className="titlebar">
                <div className="brand">
                    <span className="brand-dot" /> AI Trading Assistant
                    <span className={`eng-dot ${engineUp ? 'up' : 'down'}`} title={engineUp ? 'Engine online' : 'Engine offline'} />
                </div>
                <div className="search-wrap" ref={boxRef}>
                    <input
                        className="search-input"
                        placeholder="🔍  Search any asset — EUR/USD, Apple, BTC, Gold, Nifty…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onFocus={() => { setShowResults(true); if (!results.length) doSearch(query); }}
                    />
                    {showResults && results.length > 0 && (
                        <div className="search-results">
                            {results.map((r) => (
                                <div key={r.yahoo || r.symbol} className="search-item" onClick={() => selectAsset(r)}>
                                    <span className="si-sym">{r.symbol}</span>
                                    <span className="si-name">{r.name}</span>
                                    <span className={`si-type t-${r.type.toLowerCase()}`}>{r.type}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                <div className="win-controls">
                    <button className="tbtn" onClick={() => setScanOpen(true)} title="Scan watchlist for best setups">⊞ Scan</button>
                    <button className={`tbtn ${alertsOn ? 'on' : ''}`} onClick={() => setAlertsOn((v) => !v)} title="Alerts on new confident setups">{alertsOn ? '🔔' : '🔕'}</button>
                    <button className={`refresh-btn ${autoRefresh ? 'on' : ''}`} onClick={() => setAutoRefresh((v) => !v)} title="Auto-refresh (15s)">
                        {autoRefresh ? '⟳ auto' : '⟳ off'}
                    </button>
                    <button className="wb" onClick={() => asset && runAnalyze(asset.symbol)} title="Refresh now">↻</button>
                    <button className="wb" onClick={() => ipcRenderer.send('minimize-app')}>—</button>
                    <button className="wb" onClick={() => ipcRenderer.send('maximize-app')}>▢</button>
                    <button className="wb close" onClick={() => ipcRenderer.send('quit-app')}>✕</button>
                </div>
            </div>

            {/* ---- Scanner overlay ---- */}
            {scanOpen && (
                <div className="scan-overlay" onClick={() => setScanOpen(false)}>
                    <div className="scan-panel" onClick={(e) => e.stopPropagation()}>
                        <div className="scan-head">
                            <span>WATCHLIST SCANNER — best setups now</span>
                            <div>
                                <button className="tbtn" onClick={runScan} disabled={scanning}>{scanning ? 'scanning…' : '↻ rescan'}</button>
                                <button className="wb" onClick={() => setScanOpen(false)}>✕</button>
                            </div>
                        </div>
                        <div className="scan-list">
                            <div className="scan-row head">
                                <span>Asset</span><span>Signal</span><span>Conf</span><span>Win%</span><span>EV</span><span>Strategy</span><span></span>
                            </div>
                            {scanRows.map((r) => (
                                <div key={r.symbol} className={`scan-row ${r.signal?.toLowerCase()} ${r.stale ? 'stale' : ''}`}>
                                    <span className="sr-sym">{r.symbol}</span>
                                    <span className={`sr-sig ${r.signal?.toLowerCase()}`}>{r.stale ? '— closed' : fmtSignal(r.signal)}</span>
                                    <span>{r.confidence}</span>
                                    <span>{r.win_prob != null ? `${Math.round(r.win_prob * 100)}%` : '—'}</span>
                                    <span className={r.binary_ev > 0 ? 'pos' : 'neg'}>{r.binary_ev != null ? (r.binary_ev > 0 ? '+' : '') + r.binary_ev : '—'}</span>
                                    <span className="sr-strat">{r.strategy}</span>
                                    <button className="tbtn" onClick={() => { selectAsset({ symbol: r.symbol, name: r.symbol, type: '' }); setScanOpen(false); }}>open</button>
                                </div>
                            ))}
                            {!scanRows.length && !scanning && <div className="scan-empty">No results.</div>}
                        </div>
                    </div>
                </div>
            )}

            {/* ---- Body ---- */}
            {!asset ? (
                <Welcome onPick={selectAsset} engineUp={engineUp} />
            ) : (
                <div className="v2-body">
                    {/* Left rail */}
                    <div className="rail">
                        <div className="asset-head">
                            <div className="asset-top">
                                <span className="a-sym">{report?.symbol || asset.symbol}</span>
                                <span className={`a-type t-${(asset.type || '').toLowerCase()}`}>{asset.type}</span>
                            </div>
                            <div className="a-name">{asset.name}</div>
                            <div className="a-price">{report ? report.price : '—'}</div>
                            <div className="a-meta">
                                {report?.data_source && <span className="src-tag">{report.data_source}</span>}
                                {report?.asof && <span className="asof">@ {report.asof}</span>}
                            </div>
                        </div>

                        <div className="rail-title">TIMEFRAMES</div>
                        <div className="tf-list">
                            {(report?.timeframes || []).map((t) => (
                                <div
                                    key={t.tf}
                                    className={`tf-row ${t.signal?.toLowerCase()} ${activeTf === t.tf ? 'active' : ''}`}
                                    onClick={() => setActiveTf(t.tf)}
                                >
                                    <span className="tf-name">{t.tf}</span>
                                    <span className="tf-sig">{t.signal === 'BUY' ? '▲' : t.signal === 'SELL' ? '▼' : '•'}</span>
                                    <span className="tf-score">{t.score}%</span>
                                    <span className={`tf-trend trend-${(t.trend || '').toLowerCase()}`}>{t.trend}</span>
                                </div>
                            ))}
                        </div>

                        {overall && (
                            <div className="align-box">
                                <div className="align-label">TF ALIGNMENT</div>
                                <div className={`align-val ${sigClass}`}>{overall.alignment}</div>
                                <div className="align-bias">bias {overall.bias}</div>
                            </div>
                        )}

                        <div className="rail-title">ANALYSE TFs</div>
                        <div className="tf-chips">
                            {TIMEFRAMES.map((tf) => (
                                <button key={tf} className={`tf-chip ${tfs.includes(tf) ? 'on' : ''}`} onClick={() => toggleTf(tf)}>{tf}</button>
                            ))}
                        </div>

                        <div className="rail-title">RISK (position sizing)</div>
                        <div className="risk-row">
                            <label>Account $<input type="number" className="risk-in" value={account} onChange={(e) => setAccount(Number(e.target.value) || 0)} /></label>
                            <label>Risk %<input type="number" step="0.1" className="risk-in" value={riskPct} onChange={(e) => setRiskPct(Number(e.target.value) || 0)} /></label>
                        </div>
                    </div>

                    {/* Main */}
                    <div className="main">
                        {loading && <div className="loading">Analysing {asset.symbol} across {tfs.length} timeframes…</div>}
                        {error && <div className="err-box">{error}</div>}

                        {report && overall && (
                            <>
                                {overall.stale && (
                                    <div className="stale-banner">
                                        ⛔ MARKET CLOSED / DATA STALE — last update {fmtAge(overall.data_age_min)} ago.
                                        This feed isn’t live right now (e.g. weekend / after-hours for {asset.type}),
                                        so the signal can’t change. Try a 24/7 market like BTC/USD or ETH/USD for live analysis.
                                    </div>
                                )}
                                <div className="cards-row">
                                    <div className={`signal-card ${sigClass}`}>
                                        <div className="sc-sig">{fmtSignal(overall.signal)}</div>
                                        <div className="sc-conf">{overall.confidence} confidence</div>
                                        <div className="sc-strength">
                                            <div className="sb-track"><div className={`sb-fill ${sigClass}`} style={{ width: `${overall.strength}%` }} /></div>
                                            <span>{overall.strength}% strength · bias {overall.bias}</span>
                                        </div>
                                    </div>

                                    <div className="entry-card">
                                        <div className="ec-title">{entry?.direction && entry.direction !== '—' ? `TRADE PLAN · ${entry.direction}` : 'TRADE PLAN'}</div>
                                        {entry && entry.stop != null ? (
                                            <>
                                                <div className="ec-grid">
                                                    <div className="ec-cell"><span>ENTER</span><b>{entry.entry}</b><small>{entry.entry_time}</small></div>
                                                    <div className="ec-cell stop"><span>STOP</span><b>{entry.stop}</b><small>risk {entry.risk}</small></div>
                                                    <div className="ec-cell tgt"><span>TARGET</span><b>{entry.target}</b><small>rwd {entry.reward}</small></div>
                                                    <div className="ec-cell"><span>R:R</span><b>{entry.risk_reward ?? '—'}</b><small>exp {entry.expiry}</small></div>
                                                </div>
                                                {positionSize() && (
                                                    <div className="pos-size">
                                                        💰 Risk ${positionSize().riskAmt} ({riskPct}% of ${account}) → size <b>{positionSize().units}</b> units
                                                    </div>
                                                )}
                                            </>
                                        ) : (
                                            <div className="ec-wait">No trade — timeframes not aligned enough. Entry/exit appears when a directional setup forms.</div>
                                        )}
                                    </div>
                                </div>

                                {report.strategy && (
                                    <div className="strategy-banner">
                                        <span className="strat-name">📐 {report.strategy.name}</span>
                                        <span className="strat-desc">{report.strategy.description}</span>
                                    </div>
                                )}

                                {report.playbook && (
                                    <div className="edge-block">
                                        <div className="edge-row">
                                            <div className="edge-stat">
                                                <span className="es-label">WIN PROBABILITY</span>
                                                <div className="prob-track">
                                                    <div className="prob-be" style={{ left: `${report.playbook.breakeven_winrate * 100}%` }} title="binary break-even" />
                                                    <div className={`prob-fill ${report.playbook.win_prob > report.playbook.breakeven_winrate ? 'good' : 'bad'}`} style={{ width: `${report.playbook.win_prob * 100}%` }} />
                                                </div>
                                                <span className="es-sub">{Math.round(report.playbook.win_prob * 100)}% vs {Math.round(report.playbook.breakeven_winrate * 100)}% needed</span>
                                            </div>
                                            <div className="edge-stat sm">
                                                <span className="es-label">BINARY EV</span>
                                                <b className={report.playbook.binary_ev > 0 ? 'pos' : 'neg'}>{report.playbook.binary_ev > 0 ? '+' : ''}{report.playbook.binary_ev}</b>
                                            </div>
                                            {report.playbook.spot_ev_r != null && (
                                                <div className="edge-stat sm">
                                                    <span className="es-label">SPOT EV</span>
                                                    <b className={report.playbook.spot_ev_r > 0 ? 'pos' : 'neg'}>{report.playbook.spot_ev_r > 0 ? '+' : ''}{report.playbook.spot_ev_r}R</b>
                                                </div>
                                            )}
                                            <div className="edge-stat sm">
                                                <span className="es-label">LOCATION</span>
                                                <b className="loc">{(report.playbook.location || 'mid').replace('_', ' ')}</b>
                                            </div>
                                        </div>
                                        {report.playbook.gate_note && (
                                            <div className="gate-note">⚠ {report.playbook.gate_note}</div>
                                        )}
                                        {report.playbook.principles?.length > 0 && (
                                            <div className="principles">
                                                {report.playbook.principles.map((p, i) => (
                                                    <div key={i} className="principle" title={p.source}>
                                                        <span className="pr-text">{p.text}</span>
                                                        <span className="pr-src">{p.source}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                                <div className="chart-block">
                                    <div className="block-head">PREDICTION CHART · {activeTfData?.tf} <span className="legend"><i className="l9" />EMA9 <i className="l21" />EMA21 <i className="l50" />EMA50 <i className="lp" />prediction</span></div>
                                    <ChartCanvas data={report.chart} />
                                </div>

                                <div className="cols2">
                                    <div className="indic-block">
                                        <div className="block-head">INDICATORS · {activeTfData?.tf} <span className="muted">value · signal · expected</span></div>
                                        <div className="indic-list">
                                            {(activeTfData?.indicators || []).map((ind, i) => (
                                                <div key={i} className={`indic ${ind.signal}`}>
                                                    <span className="i-dot">{ind.signal === 'bull' ? '▲' : ind.signal === 'bear' ? '▼' : '•'}</span>
                                                    <span className="i-name">{ind.name}</span>
                                                    <span className="i-val">{ind.value}</span>
                                                    <span className="i-exp">{ind.expected}</span>
                                                </div>
                                            ))}
                                            {activeTfData?.pattern && <div className="indic pattern">📊 Candle pattern: <b>{activeTfData.pattern}</b></div>}
                                        </div>
                                    </div>

                                    <div className="report-block">
                                        <div className="block-head">ANALYSIS REPORT</div>
                                        <pre className="report-text">{report.report}</pre>
                                        {report.model?.prob != null && (
                                            <div className="model-line">🧠 AI model P(up) {Math.round(report.model.prob * 100)}% · {report.model.eligible ? 'active' : 'info only'}</div>
                                        )}
                                    </div>
                                </div>

                                {/* Backtest — measured edge on history */}
                                <div className="bt-block">
                                    <div className="block-head">
                                        STRATEGY BACKTEST <span className="muted">measured edge on history (no look-ahead)</span>
                                        <button className="tbtn" onClick={runBacktest} disabled={btLoading}>{btLoading ? 'running…' : '▶ run backtest'}</button>
                                    </div>
                                    {backtest?.error && <div className="muted">{backtest.error}</div>}
                                    {backtest?.summary && (
                                        <>
                                            <div className="bt-summary">
                                                <div className="bt-stat"><span>TRADES</span><b>{backtest.summary.trades}</b></div>
                                                <div className="bt-stat"><span>WIN-RATE</span><b className={backtest.summary.win_rate >= 54 ? 'pos' : 'neg'}>{backtest.summary.win_rate}%</b></div>
                                                <div className="bt-stat"><span>EXPECTANCY</span><b className={backtest.summary.expectancy_r > 0 ? 'pos' : 'neg'}>{backtest.summary.expectancy_r}R</b></div>
                                                <div className="bt-stat"><span>BINARY EV</span><b className={backtest.summary.binary_ev > 0 ? 'pos' : 'neg'}>{backtest.summary.binary_ev}</b></div>
                                                <div className="bt-stat"><span>TOTAL</span><b className={backtest.summary.total_r > 0 ? 'pos' : 'neg'}>{backtest.summary.total_r}R</b></div>
                                            </div>
                                            <div className="bt-rows">
                                                {backtest.per_tf.map((p) => (
                                                    <div key={p.tf} className="bt-row">
                                                        <span className="btr-tf">{p.tf}</span>
                                                        <span>{p.trades} trades</span>
                                                        <span className={p.win_rate >= 54 ? 'pos' : 'neg'}>{p.win_rate}% WR</span>
                                                        <span className={p.expectancy_r > 0 ? 'pos' : 'neg'}>{p.expectancy_r}R exp</span>
                                                        <span>PF {p.profit_factor}</span>
                                                        <span className="neg">DD {p.max_drawdown_r}R</span>
                                                    </div>
                                                ))}
                                            </div>
                                            <div className="bt-note">Backtest uses the same engine, no look-ahead. Past performance ≠ future results.</div>
                                        </>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* ---- Footer ---- */}
            <div className="footer">
                {report?.stats ? (
                    <>
                        <span>Signals: {report.stats.total_signals ?? 0}</span>
                        <span>Win-rate: {report.stats.win_rate != null
                            ? `${report.stats.win_rate}% (${report.stats.wins ?? 0}W/${report.stats.losses ?? 0}L)`
                            : 'building'}</span>
                        {report.stats.flats ? <span className="muted">flat {report.stats.flats}</span> : null}
                        <span>Open: {report.stats.pending ?? 0}</span>
                        {overall?.data_age_min != null && (
                            <span className={overall.stale ? 'stale-dot' : 'muted'}>
                                data {fmtAge(overall.data_age_min)} old{overall.stale ? ' · STALE' : ''}
                            </span>
                        )}
                        {report.latency_ms != null && <span className="muted">· {report.latency_ms}ms</span>}
                    </>
                ) : (
                    <span className="muted">Advisory only · not financial advice · real-market data</span>
                )}
            </div>
        </div>
    );
}

function Welcome({ onPick, engineUp }) {
    const popular = [
        { symbol: 'EUR/USD', name: 'Euro / US Dollar', type: 'FX' },
        { symbol: 'GBP/USD', name: 'British Pound / US Dollar', type: 'FX' },
        { symbol: 'USD/JPY', name: 'US Dollar / Japanese Yen', type: 'FX' },
        { symbol: 'BTC/USD', name: 'Bitcoin', type: 'Crypto' },
        { symbol: 'ETH/USD', name: 'Ethereum', type: 'Crypto' },
        { symbol: 'AAPL', name: 'Apple Inc.', type: 'Stock' },
        { symbol: 'TSLA', name: 'Tesla Inc.', type: 'Stock' },
        { symbol: 'GC=F', name: 'Gold (Futures)', type: 'Commodity' },
    ];
    return (
        <div className="welcome">
            <div className="w-logo">📈</div>
            <h1>Select an asset to analyse</h1>
            <p>Search any currency pair, stock, crypto, index or commodity above — the AI fetches real candles and runs a full multi-timeframe analysis.</p>
            {!engineUp && <div className="w-warn">⚠ Waiting for the analysis engine to come online…</div>}
            <div className="w-title">Popular</div>
            <div className="w-grid">
                {popular.map((p) => (
                    <button key={p.symbol} className="w-card" onClick={() => onPick(p)}>
                        <span className="wc-sym">{p.symbol}</span>
                        <span className="wc-name">{p.name}</span>
                        <span className={`wc-type t-${p.type.toLowerCase()}`}>{p.type}</span>
                    </button>
                ))}
            </div>
        </div>
    );
}
