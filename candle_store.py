"""SQLite storage for 1-minute OHLCV market data.

The database is intentionally append/upsert based so the bot can keep a rolling
90-day history and the backtester can later replay the exact 1m candles.
"""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from config import CANDLE_DB_PATH, CANDLE_RETENTION_DAYS

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles_1m (
    symbol TEXT NOT NULL,
    ts INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_candles_1m_symbol_ts ON candles_1m(symbol, ts);
CREATE INDEX IF NOT EXISTS idx_candles_1m_ts ON candles_1m(ts);
"""


def _is_valid_sqlite(path: Path) -> bool:
    """Return True only if path exists and is a readable SQLite database."""
    if not path.is_file() or path.stat().st_size < 100:
        return False
    try:
        with path.open("rb") as f:
            header = f.read(16)
        # Git LFS pointer files start with text, not "SQLite format 3"
        if not header.startswith(b"SQLite format 3"):
            return False
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        try:
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def _reset_database(path: Path) -> None:
    """Remove a corrupt / LFS-pointer / non-SQLite file so a fresh DB can be created."""
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = Path(str(path) + suffix) if suffix else path
        try:
            if p.exists():
                p.unlink()
                logger.warning("Removed invalid DB file: %s", p)
        except OSError as exc:
            logger.warning("Could not remove %s: %s", p, exc)


def connect(db_path=None):
    path = Path(db_path or CANDLE_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists() and not _is_valid_sqlite(path):
        logger.warning(
            "%s is not a valid SQLite database (corrupt or Git LFS pointer). Recreating empty DB.",
            path,
        )
        _reset_database(path)

    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
    except sqlite3.DatabaseError:
        conn.close()
        logger.warning("SQLite open failed for %s; recreating.", path)
        _reset_database(path)
        conn = sqlite3.connect(str(path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
    return conn


def upsert_candles(candles_by_symbol):
    """Insert/update candles. Input: {symbol: [{t,o,c,h,l,v}, ...]}"""
    total = 0
    with connect() as conn:
        for symbol, candles in candles_by_symbol.items():
            rows = [
                (symbol, int(c["t"]), float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"]), float(c["v"]))
                for c in candles
            ]
            if rows:
                conn.executemany(
                    """INSERT INTO candles_1m(symbol,ts,open,high,low,close,volume)
                       VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(symbol,ts) DO UPDATE SET
                         open=excluded.open, high=excluded.high, low=excluded.low,
                         close=excluded.close, volume=excluded.volume""",
                    rows,
                )
                total += len(rows)
    return total


def prune_old_candles(now_epoch=None, retention_days=CANDLE_RETENTION_DAYS):
    now_epoch = int(now_epoch or time.time())
    cutoff = now_epoch - int(retention_days) * 86400
    with connect() as conn:
        cur = conn.execute("DELETE FROM candles_1m WHERE ts < ?", (cutoff,))
        deleted = cur.rowcount
        try:
            conn.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
    return deleted


def latest_timestamp(symbol):
    with connect() as conn:
        row = conn.execute("SELECT MAX(ts) FROM candles_1m WHERE symbol=?", (symbol,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def earliest_timestamp(symbol):
    with connect() as conn:
        row = conn.execute("SELECT MIN(ts) FROM candles_1m WHERE symbol=?", (symbol,)).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def load_candles(symbol, start_at=None, end_at=None, db_path=None):
    sql = "SELECT ts,open,high,low,close,volume FROM candles_1m WHERE symbol=?"
    args = [symbol]
    if start_at is not None:
        sql += " AND ts>=?"
        args.append(int(start_at))
    if end_at is not None:
        sql += " AND ts<=?"
        args.append(int(end_at))
    sql += " ORDER BY ts"
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [{"t": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]} for r in rows]


def database_stats():
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM candles_1m").fetchone()[0]
        symbols = conn.execute("SELECT COUNT(DISTINCT symbol) FROM candles_1m").fetchone()[0]
        earliest = conn.execute("SELECT MIN(ts) FROM candles_1m").fetchone()[0]
        latest = conn.execute("SELECT MAX(ts) FROM candles_1m").fetchone()[0]
    return {"candles": total, "symbols": symbols, "earliest": earliest, "latest": latest}
