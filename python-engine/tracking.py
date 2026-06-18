"""
Signal + outcome tracking store (Phase-1 keystone).

Logs every confirmed signal so the system becomes *measurable* and, later, trainable.
Outcomes (win/loss at expiry) are recorded by `record_outcome`; until an outcome feed
is wired, the win-rate widget honestly shows "pending". SQLite = zero-setup, file-based.
"""
import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).with_name("signals.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL NOT NULL,
    platform      TEXT,
    symbol        TEXT,
    timeframe     TEXT,
    direction     TEXT,          -- BUY / SELL
    confidence    TEXT,
    setup_score   INTEGER,
    entry_price   TEXT,
    expiry_time   TEXT,
    confluence    TEXT,          -- json list
    indicators    TEXT,          -- json breakdown
    model_version TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
    signal_id   INTEGER PRIMARY KEY,
    settle_ts   REAL,
    settle_price TEXT,
    result      TEXT,            -- win / loss / flat
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);
"""


class Tracker:
    def __init__(self, db_path=DB_PATH):
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()   # serialise access — one conn, many threads

    def log_signal(self, result, context, model_version="confluence-v1"):
        """Persist a confirmed BUY/SELL. Returns row id (or None if not loggable)."""
        if result.get("signal") not in ("BUY", "SELL"):
            return None
        ctx = context or {}
        setup = result.get("trade_setup") or {}
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO signals
                   (ts, platform, symbol, timeframe, direction, confidence, setup_score,
                    entry_price, expiry_time, confluence, indicators, model_version)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    time.time(),
                    ctx.get("platform"),
                    ctx.get("symbol"),
                    ctx.get("timeframe"),
                    result.get("signal"),
                    result.get("confidence"),
                    int(result.get("setup_score") or 0),
                    str(ctx.get("current_price") or setup.get("entry") or ""),
                    setup.get("expiry_time") or ctx.get("expiry_time"),
                    json.dumps(result.get("confluence") or []),
                    json.dumps(result.get("indicators") or []),
                    model_version,
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def record_outcome(self, signal_id, settle_price, result):
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO outcomes (signal_id, settle_ts, settle_price, result)
                   VALUES (?,?,?,?)""",
                (signal_id, time.time(), str(settle_price), result),
            )
            self._conn.commit()

    def stats(self, limit=100):
        """Recent win-rate over signals that have outcomes recorded."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT o.result FROM outcomes o
                   JOIN signals s ON s.id = o.signal_id
                   ORDER BY o.settle_ts DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            total_signals = self._conn.execute(
                "SELECT COUNT(*) FROM signals"
            ).fetchone()[0]
        settled = [r[0] for r in rows]
        wins = sum(1 for r in settled if r == "win")
        losses = sum(1 for r in settled if r == "loss")
        flats = sum(1 for r in settled if r == "flat")
        decided = wins + losses                 # flats (no move) excluded from win-rate
        win_rate = round(100 * wins / decided, 1) if decided else None
        return {
            "total_signals": total_signals,
            "settled": len(settled),
            "wins": wins,
            "losses": losses,
            "flats": flats,
            "win_rate": win_rate,           # None until win/loss outcomes exist
            "breakeven_note": "Binary options: ~53–59% needed to break even",
        }

    def close(self):
        self._conn.close()
