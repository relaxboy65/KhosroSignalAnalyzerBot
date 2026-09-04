import asyncio
import logging
import sys
import time
from datetime import datetime, timezone

import aiohttp

from config import (
    SYMBOLS, VERSION, TIMEFRAMES, LEVERAGE, MARGIN_USD,
    BROKER_FEE_RATE, SLIPPAGE_PCT, RESOLUTION_TIMEFRAME,
    TELEGRAM_MIN_INTERVAL_SECONDS,
    CANDLE_RETENTION_DAYS, RESOLUTION_LOOKBACK_DAYS,
)
from rules import analyze_market, send_to_telegram
from signal_store import append_signal_row, tehran_time_str, load_open_signals, resolve_signal
from telegram_ui import signal_message, resolution_message
from candle_store import upsert_candles, load_candles, latest_timestamp, prune_old_candles

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('bot_log.txt', encoding='utf-8'), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
KUCOIN_URL = 'https://api.kucoin.com/api/v1/market/candles'
INTERVALS = {'5m': '5min', '15m': '15min', '30m': '30min', '1h': '1hour', '4h': '4hour'}
LOOKBACK_DAYS = {'5m': 7, '15m': 14, '30m': 30, '1h': 60, '4h': 180}
RESOLUTION_SECONDS = 60
KUCOIN_MAX_CANDLES = 1490


def _price_pnl(row, exit_price):
    entry = float(row['entry_price'])
    notional = float(row.get('notional_usd') or MARGIN_USD * LEVERAGE)
    direction = row['direction'].upper()
    ret = (exit_price - entry) / entry if direction == 'LONG' else (entry - exit_price) / entry
    fee = notional * BROKER_FEE_RATE * 2
    return notional * ret - fee, fee


def _adjust_exit_for_slippage(direction, price):
    return price * (1 - SLIPPAGE_PCT) if direction == 'LONG' else price * (1 + SLIPPAGE_PCT)


async def fetch_timeframe(session, symbol, tf, days):
    end = int(datetime.now(timezone.utc).timestamp())
    start = end - days * 86400
    return await fetch_klines(session, symbol, tf, start, end)


async def fetch_klines(session, symbol, tf, start_at, end_at):
    """Paginated KuCoin OHLCV fetch. Returns (candles, success)."""
    interval_seconds = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400}[tf]
    interval_name = {'1m': '1min', **INTERVALS}[tf]
    cursor = max(0, int(start_at))
    end_at = int(end_at)
    all_rows = []
    while cursor < end_at:
        page_end = min(end_at, cursor + interval_seconds * KUCOIN_MAX_CANDLES)
        params = {'symbol': symbol, 'type': interval_name, 'startAt': cursor, 'endAt': page_end}
        raw = None
        for attempt in range(5):
            try:
                async with session.get(KUCOIN_URL, params=params, timeout=30) as r:
                    if r.status == 429:
                        retry = 2 ** attempt
                        logger.warning('KuCoin 429 %s %s; retrying in %ss', symbol, tf, retry)
                        await asyncio.sleep(retry)
                        continue
                    if r.status != 200:
                        logger.warning('KuCoin %s %s HTTP %s', symbol, tf, r.status)
                        return [], False
                    raw = (await r.json()).get('data', [])
                    break
            except Exception as exc:
                logger.warning('KuCoin %s %s fetch error attempt=%d: %s', symbol, tf, attempt + 1, exc)
                if attempt < 4:
                    await asyncio.sleep(min(2 ** attempt, 8))
        if raw is None:
            return [], False
        rows = [
            {'t': int(x[0]), 'o': float(x[1]), 'c': float(x[2]), 'h': float(x[3]), 'l': float(x[4]), 'v': float(x[5])}
            for x in raw
        ]
        if not rows:
            break
        all_rows.extend(rows)
        newest = max(x['t'] for x in rows)
        if newest < cursor + interval_seconds:
            break
        cursor = newest + interval_seconds
        if len(rows) < KUCOIN_MAX_CANDLES:
            # A short page means there is no more data in this requested range.
            if page_end >= end_at:
                break
    unique = {x['t']: x for x in all_rows}
    now = int(datetime.now(timezone.utc).timestamp())
    candles = [x for t, x in sorted(unique.items()) if t + interval_seconds <= now and start_at <= t <= end_at]
    return candles, True


async def fetch_symbol(session, symbol):
    out = {}
    for tf in TIMEFRAMES:
        k, v = await fetch_timeframe(session, symbol, tf, LOOKBACK_DAYS[tf])
        if v:
            out[k] = v
    return out


def _resolve_from_1m(row, candles):
    """Return first closed 1m TP/SL event after the signal, without look-ahead."""
    issued = int(float(row.get('issued_at_epoch') or 0))
    last_checked = int(float(row.get('last_checked_epoch') or max(0, issued - 60)))
    entry = float(row['entry_price'])
    sl = float(row['stop_loss'])
    tp = float(row['take_profit'])
    direction = row['direction'].upper()
    latest_checked = last_checked
    for candle in candles:
        t = int(candle['t'])
        if t <= max(issued, last_checked):
            continue
        latest_checked = max(latest_checked, t)
        hit_sl = candle['l'] <= sl if direction == 'LONG' else candle['h'] >= sl
        hit_tp = candle['h'] >= tp if direction == 'LONG' else candle['l'] <= tp
        if hit_sl and hit_tp:
            outcome, raw_exit = 'STOP_HIT', sl
        elif hit_sl:
            outcome, raw_exit = 'STOP_HIT', sl
        elif hit_tp:
            outcome, raw_exit = 'TP_HIT', tp
        else:
            continue
        exit_price = _adjust_exit_for_slippage(direction, raw_exit)
        pnl, fee = _price_pnl(row, exit_price)
        return outcome, exit_price, pnl, fee, t, latest_checked
    return None, None, None, None, latest_checked, latest_checked


def _update_last_checked(row, epoch):
    """Persist progress even when a trade remains OPEN, so each run only scans new 1m candles."""
    from signal_store import update_last_checked
    return update_last_checked(row, epoch)


async def _sync_1m_symbol(session, symbol, days_if_empty=RESOLUTION_LOOKBACK_DAYS):
    """Keep the local 1m SQLite cache current. Empty symbols get a small safety
    backfill; use collect_1m_data.py for the full 90-day initial backfill."""
    now = int(datetime.now(timezone.utc).timestamp())
    latest = latest_timestamp(symbol)
    start = latest + RESOLUTION_SECONDS if latest is not None else now - days_if_empty * 86400
    if start >= now - RESOLUTION_SECONDS:
        return True
    candles, success = await fetch_klines(session, symbol, RESOLUTION_TIMEFRAME, start, now)
    if not success:
        return False
    upsert_candles({symbol: candles})
    return True


async def resolve_previous_signals(session, open_rows):
    if not open_rows:
        return 0
    by_symbol = {}
    for row in open_rows:
        by_symbol.setdefault(row['symbol'], []).append(row)
    resolved = 0
    for symbol, rows in by_symbol.items():
        if not await _sync_1m_symbol(session, symbol):
            logger.warning('%s: 1m resolution data unavailable; keeping OPEN and not advancing checkpoint', symbol)
            continue
        start = min(int(float(r.get('last_checked_epoch') or r.get('issued_at_epoch') or 0)) for r in rows)
        end = int(datetime.now(timezone.utc).timestamp())
        candles = load_candles(symbol, start_at=start, end_at=end)
        for row in rows:
            outcome, exit_price, pnl, fee, hit_epoch, checkpoint = _resolve_from_1m(row, candles)
            if outcome:
                hit_dt = datetime.fromtimestamp(hit_epoch, timezone.utc)
                margin = float(row.get('position_margin_usd') or MARGIN_USD)
                lev = float(row.get('leverage') or LEVERAGE)
                msg = resolution_message(row, outcome, exit_price, pnl, fee, margin, lev)
                reply_to = row.get('telegram_message_id') or None
                resolution_id = await send_to_telegram(msg, reply_to_message_id=reply_to)
                if resolution_id is None:
                    logger.warning('%s: resolution message failed; keeping trade OPEN for retry', symbol)
                    continue
                if resolve_signal(row, tehran_time_str(hit_dt), exit_price, pnl, fee, outcome, resolution_id):
                    resolved += 1
                    logger.info('RESOLVED %s %s -> %s pnl=%.4f', symbol, row['direction'], outcome, pnl)
            else:
                _update_last_checked(row, checkpoint)
                logger.info('OPEN %s %s checkpoint=%s', symbol, row['direction'], checkpoint)
    return resolved


async def process_symbol(session, symbol, open_by_symbol):
    if open_by_symbol.get(symbol):
        logger.info('%s: previous signal still OPEN; waiting for resolution', symbol)
        return
    data = await fetch_symbol(session, symbol)
    if '30m' not in data or len(data['30m']) < 80:
        logger.info('%s: insufficient data', symbol)
        return
    candidates = [analyze_market(symbol, data, d, 'MEDIUM') for d in ('LONG', 'SHORT')]
    candidates = [x for x in candidates if x.get('status') == 'SIGNAL']
    if not candidates:
        logger.info('%s: no signal', symbol)
        return
    result = max(candidates, key=lambda x: x['score'])
    time_str = tehran_time_str()
    msg = signal_message(result, VERSION, MARGIN_USD, LEVERAGE)
    telegram_id = await send_to_telegram(msg)
    append_signal_row(
        symbol, result['direction'], result['risk'], result['price'], result['stop_loss'],
        result['take_profit'], time_str, result['signal_source'],
        position_margin_usd=MARGIN_USD, leverage=LEVERAGE,
        telegram_message_id=telegram_id, issued_at_epoch=int(datetime.now(timezone.utc).timestamp())
    )
    logger.info(
        'SIGNAL %s %s score=%.1f risk=%s entry=%.8f SL=%.8f TP=%.8f margin=$%.2f notional=$%.2f tg=%s',
        symbol, result['direction'], result['score'], result['risk'], result['price'],
        result['stop_loss'], result['take_profit'], MARGIN_USD, MARGIN_USD * LEVERAGE, telegram_id
    )


async def main_async():
    connector = aiohttp.TCPConnector(limit=8)
    async with aiohttp.ClientSession(connector=connector) as session:
        prune_old_candles()
        open_rows = load_open_signals()
        logger.info('Checking %d previous OPEN signal(s) with 1m candles before new signals', len(open_rows))
        await resolve_previous_signals(session, open_rows)
        open_rows = load_open_signals()
        open_by_symbol = {}
        for row in open_rows:
            open_by_symbol.setdefault(row['symbol'], []).append(row)
        for symbol in SYMBOLS:
            try:
                await process_symbol(session, symbol, open_by_symbol)
            except Exception:
                logger.exception('processing failed for %s', symbol)


if __name__ == '__main__':
    asyncio.run(main_async())
