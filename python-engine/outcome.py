"""
Outcome capture — symbol-aware, persistent feedback loop.

When a BUY/SELL is logged we store (symbol, direction, entry, settle_epoch) in SQLite.
A background settler later fetches the LATEST price *for that symbol* and labels
win/loss/flat. Persisting + keying by symbol fixes two earlier bugs: pendings were
lost on restart, and one symbol's signal could be settled against another symbol's
price. Flats (no move) are excluded from the win-rate upstream.
"""
import re
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).with_name("signals.db")


def tf_to_seconds(tf, default=60):
    if not tf or str(tf).upper() == "UNKNOWN":
        return default
    t = str(tf).lower().strip()
    n = int(re.sub(r"\D", "", t) or "1")
    if t.endswith("s"):
        return max(n, 5)
    if t.endswith("m"):
        return max(n, 1) * 60
    if t.endswith("h"):
        return max(n, 1) * 3600
    if t.endswith("d"):
        return max(n, 1) * 86400
    return default


def to_float(price):
    try:
        return float(str(price).replace(",", ""))
    except (TypeError, ValueError):
        return None


class OutcomeTracker:
    def __init__(self, db_path=DB_PATH, grace_sec=86400):
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS pending_outcomes (
                   signal_id    INTEGER PRIMARY KEY,
                   symbol       TEXT,
                   direction    TEXT,
                   entry        REAL,
                   settle_epoch REAL
               )"""
        )
        self._conn.commit()
        self._grace = grace_sec
        self._lock = threading.Lock()

    def add(self, signal_id, symbol, direction, entry_price, settle_epoch):
        entry = to_float(entry_price)
        if signal_id is None or entry is None:
            return False
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO pending_outcomes VALUES (?,?,?,?,?)",
                (signal_id, symbol, direction, entry, settle_epoch),
            )
            self._conn.commit()
        return True

    def due(self, now):
        """Pendings whose settle time has passed: list of (id, symbol, dir, entry, epoch)."""
        with self._lock:
            return self._conn.execute(
                "SELECT signal_id, symbol, direction, entry, settle_epoch "
                "FROM pending_outcomes WHERE settle_epoch <= ?",
                (now,),
            ).fetchall()

    @staticmethod
    def result_for(direction, entry, settle_price):
        if settle_price == entry:
            return "flat"
        if direction == "BUY":
            return "win" if settle_price > entry else "loss"
        return "win" if settle_price < entry else "loss"

    def remove(self, signal_id):
        with self._lock:
            self._conn.execute("DELETE FROM pending_outcomes WHERE signal_id=?", (signal_id,))
            self._conn.commit()

    def pending_count(self):
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM pending_outcomes").fetchone()[0]
