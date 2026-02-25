# bot.py - نسخه نهایی با SAFE V3 + لاگ کامل مثل قبل

import aiohttp
import asyncio
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from config import SYMBOLS
from indicators import calculate_rsi, calculate_ema, calculate_macd, calculate_atr, calculate_adx
from rules import generate_signal

# ========== تنظیمات لاگ ==========
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_log.txt", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

KUCOIN_URL = "https://api.kucoin.com/api/v1/market/candles"

intervals = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1hour",
    "4h": "4hour"
}

# ========== دریافت داده ==========
async def fetch_timeframe(session, symbol, tf, days):
    api_tf = intervals[tf]
    end_time = int(datetime.utcnow().timestamp())
    start_time = end_time - days * 24 * 3600
    params = {"symbol": symbol, "type": api_tf, "startAt": start_time, "endAt": end_time}
    try:
        async with session.get(KUCOIN_URL, params=params, timeout=20) as resp:
            if resp.status == 200:
                data = await resp.json()
                candles_raw = data.get("data", [])
                parsed = [
                    {'t': int(c[0]), 'o': float(c[1]), 'c': float(c[2]),
                     'h': float(c[3]), 'l': float(c[4]), 'v': float(c[5])}
                    for c in candles_raw
                ]
                return tf, list(reversed(parsed))
            else:
                logger.warning(f"خطای HTTP {resp.status} برای {symbol} {tf}")
                return tf, []
    except Exception as e:
        logger.error(f"خطا در دریافت {symbol} {tf}: {e}")
        return tf, []

async def fetch_all_timeframes(session, symbol):
    settings = {"1m": 2, "5m": 7, "15m": 7, "30m": 14, "1h": 30, "4h": 60}
    tasks = [fetch_timeframe(session, symbol, tf, days) for tf, days in settings.items()]
    results = await asyncio.gather(*tasks)
    return {tf: candles for tf, candles in results if candles}

# ========== پردازش نماد + لاگ کامل مثل قبل ==========
async def process_symbol(symbol, data, index, total):
    if not data or "30m" not in data or len(data["30m"]) < 20:
        logger.info(f"[{index}/{total}] {symbol} — ❌ داده کافی نیست")
        return

    # محاسبات اندیکاتورها
    closes_30 = [c['c'] for c in data["30m"]]
    ema21_30m = calculate_ema(closes_30, 21)
    ema50_30m = calculate_ema(closes_30, 50)
    ema8_30m = calculate_ema(closes_30, 8)

    candle_15m = data.get("15m", [{}])[-1]
    candle_5m = data.get("5m", [{}])[-1]
    candle_1m = data.get("1m", [{}])[-1]

    closes_1h = [c['c'] for c in data.get("1h", [])]
    ema21_1h = calculate_ema(closes_1h, 21) if closes_1h else None
    ema50_1h = calculate_ema(closes_1h, 50) if closes_1h else None

    closes_4h = [c['c'] for c in data.get("4h", [])]
    ema21_4h = calculate_ema(closes_4h, 21) if closes_4h else None
    ema50_4h = calculate_ema(closes_4h, 50) if closes_4h else None
    ema200_4h = calculate_ema(closes_4h, 200) if closes_4h else None

    macd_30m = calculate_macd(closes_30)
    rsi_30m = calculate_rsi(closes_30)
    atr_30m = calculate_atr(data["30m"]) if "30m" in data else 0.0
    adx_val, di_plus, di_minus = calculate_adx(data["30m"]) if data.get("30m") else (0, 0, 0)

    price_30m = closes_30[-1]

    # ==================== صدا زدن SAFE V3 ====================
    signal = await generate_signal(
        symbol=symbol,
        direction="LONG" if ema21_30m and ema50_30m and ema21_30m > ema50_30m else "SHORT",
        price_30m=price_30m,
        ema21_1h=ema21_1h,
        ema50_1h=ema50_1h,
        ema21_4h=ema21_4h,
        ema50_4h=ema50_4h,
        adx=adx_val,
        di_plus=di_plus,
        di_minus=di_minus,
        ema21_30m=ema21_30m,
        rsi_30m=rsi_30m,
        candles_30m=data["30m"],
        atr_30m=atr_30m
    )

    # لاگ کامل مثل قبل (حتی اگر NO_SIGNAL باشد)
    logger.info("=" * 80)
    logger.info(f"📊 سیگنال {symbol} | جهت={signal.get('direction', 'UNKNOWN')} | وضعیت={signal.get('status')}")
    
    if signal.get("status") == "SIGNAL":
        logger.info(f"✅ سیگنال قوی صادر شد | ورود={signal['price']:.4f} | استاپ={signal['stop_loss']:.4f} | تارگت={signal['take_profit']:.4f} | RR={signal.get('rr', 2.3)}")
        logger.info(f"📈 مدل: {signal.get('reason', 'SAFE_PULLBACK_V3')}")
    else:
        logger.info(f"📭 بدون سیگنال — دلیل: {signal.get('reason', 'نامشخص')}")

    logger.info("=" * 80)

# ========== تابع اصلی ==========
async def main_async():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_all_timeframes(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*tasks)
        for idx, data in enumerate(results, 1):
            await process_symbol(SYMBOLS[idx-1], data, idx, len(SYMBOLS))

if __name__ == "__main__":
    asyncio.run(main_async())
