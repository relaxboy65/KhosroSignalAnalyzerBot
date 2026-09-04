"""Download and maintain the rolling 90-day 1m OHLCV SQLite database.

Usage examples:
  python collect_1m_data.py                 # sync configured symbols for 90 days if needed
  python collect_1m_data.py --days 90       # explicit initial history window
  python collect_1m_data.py --symbol BTC-USDT --days 90
  python collect_1m_data.py --loop --interval 120   # continuous collector, separate process
"""
from __future__ import annotations
import argparse
import asyncio
import time
from datetime import datetime, timezone

import aiohttp

from bot import fetch_klines
from candle_store import upsert_candles, prune_old_candles, database_stats, latest_timestamp
from config import SYMBOLS, CANDLE_RETENTION_DAYS


async def sync_symbol(session, symbol, days):
    now = int(datetime.now(timezone.utc).timestamp())
    latest = latest_timestamp(symbol)
    start = latest + 60 if latest is not None else now - days * 86400
    if start >= now - 60:
        return 0
    candles, ok = await fetch_klines(session, symbol, '1m', start, now)
    if not ok:
        print(f'{symbol}: download failed')
        return 0
    n = upsert_candles({symbol: candles})
    print(f'{symbol}: {n} 1m candles synced')
    return n


async def sync_all(symbols, days):
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=8)) as session:
        total = 0
        for symbol in symbols:
            total += await sync_symbol(session, symbol, days)
    deleted = prune_old_candles()
    stats = database_stats()
    print(f'Collector cycle complete: synced={total}, pruned={deleted}, stats={stats}')
    return total


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol', default='', help='Optional symbol, e.g. BTC-USDT')
    ap.add_argument('--days', type=int, default=CANDLE_RETENTION_DAYS)
    ap.add_argument('--loop', action='store_true', help='Keep running as a separate collector process')
    ap.add_argument('--interval', type=int, default=120, help='Seconds between collector cycles (default: 120)')
    args = ap.parse_args()
    if args.interval < 60:
        ap.error('--interval must be at least 60 seconds')
    symbols = [args.symbol] if args.symbol else SYMBOLS
    if not args.loop:
        await sync_all(symbols, args.days)
        return
    print(f'1m collector started: {len(symbols)} symbols, interval={args.interval}s, retention={CANDLE_RETENTION_DAYS}d')
    while True:
        started = time.monotonic()
        try:
            await sync_all(symbols, args.days)
        except Exception as exc:
            print(f'Collector cycle failed: {exc}')
        elapsed = time.monotonic() - started
        await asyncio.sleep(max(1, args.interval - elapsed))


if __name__ == '__main__':
    asyncio.run(main())
