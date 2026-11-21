"""Persistencia del paper trading en SQLite.

Guarda el estado de la cuenta, las operaciones cerradas, la curva de capital y
un registro de eventos (señales, órdenes, errores, pausas) para auditoría y para
la web de seguimiento. Usa modo WAL para que la web pueda leer mientras el bot
escribe desde otro proceso.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from btcbot.backtest.broker import AccountState, Trade

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_time TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_time TEXT NOT NULL,
    exit_price REAL NOT NULL,
    units REAL NOT NULL,
    stop REAL NOT NULL,
    pnl REAL NOT NULL,
    net_return REAL NOT NULL,
    exit_reason TEXT NOT NULL,
    bars INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS equity (
    ts TEXT PRIMARY KEY,
    equity REAL NOT NULL,
    close REAL NOT NULL,
    in_position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL
);
"""


def _iso(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


class PaperStore:
    def __init__(self, path: Path | str, readonly: bool = False):
        self.path = Path(path)
        if readonly:
            uri = f"file:{self.path}?mode=ro"
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path, check_same_thread=False,
                                         isolation_level=None)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0

    def close(self) -> None:
        self._conn.close()

    def backup_to(self, path: Path | str) -> None:
        """Copia consistente de toda la base (API de backup de SQLite)."""
        with self._lock:
            dest = sqlite3.connect(path)
            try:
                self._conn.backup(dest)
            finally:
                dest.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Agrupa escrituras: o se guardan todas o ninguna (p. ej. si el proceso muere)."""
        with self._lock:
            outer = self._depth == 0
            if outer:
                self._conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if outer:
                    self._conn.execute("ROLLBACK")
                raise
            self._depth -= 1
            if outer:
                self._conn.execute("COMMIT")

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    # --- clave/valor ---------------------------------------------------------
    def get(self, key: str, default=None):
        row = self._exec("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key: str, value) -> None:
        self._exec("INSERT INTO kv (key, value) VALUES (?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                   (key, json.dumps(value)))

    # --- estado --------------------------------------------------------------
    def load_state(self) -> AccountState | None:
        d = self.get("account")
        return AccountState.from_dict(d) if d else None

    def save_state(self, state: AccountState) -> None:
        self.set("account", state.to_dict())

    def last_candle(self) -> pd.Timestamp | None:
        v = self.get("last_candle")
        return pd.Timestamp(v) if v else None

    def set_last_candle(self, ts: pd.Timestamp) -> None:
        self.set("last_candle", _iso(ts))

    @property
    def paused(self) -> bool:
        return bool(self.get("paused", False))

    def set_paused(self, value: bool) -> None:
        self.set("paused", value)

    # --- registros -----------------------------------------------------------
    def add_trade(self, t: Trade) -> None:
        self._exec(
            "INSERT INTO trades (entry_time, entry_price, exit_time, exit_price, units, stop, "
            "pnl, net_return, exit_reason, bars) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_iso(t.entry_time), t.entry_price, _iso(t.exit_time), t.exit_price, t.units,
             t.stop, t.pnl, t.net_return, t.exit_reason, t.bars),
        )

    def add_equity(self, ts: pd.Timestamp, equity: float, close: float, in_position: bool) -> None:
        self._exec("INSERT OR REPLACE INTO equity (ts, equity, close, in_position) "
                   "VALUES (?, ?, ?, ?)", (_iso(ts), equity, close, int(in_position)))

    def add_event(self, ts: pd.Timestamp, level: str, kind: str, message: str) -> None:
        self._exec("INSERT INTO events (ts, level, kind, message) VALUES (?, ?, ?, ?)",
                   (_iso(ts), level, kind, message))

    # --- lecturas para reportes y web ---------------------------------------
    def trades(self) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM trades ORDER BY id", self._conn)
        for col in ("entry_time", "exit_time"):
            df[col] = pd.to_datetime(df[col], utc=True)
        return df

    def equity(self) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM equity ORDER BY ts", self._conn)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df.set_index("ts")

    def events(self, limit: int = 50) -> pd.DataFrame:
        df = pd.read_sql_query("SELECT * FROM events ORDER BY id DESC LIMIT ?", self._conn,
                               params=(limit,))
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df
