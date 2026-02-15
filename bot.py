# bot.py - نسخه جدید با چک همزمان LONG و SHORT برای هر نماد
import aiohttp
import asyncio
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from config import SYMBOLS
from indicators import calculate_rsi, calculate_ema, calculate_macd, calculate_atr
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

# ========== دریافت داده برای یک تایم‌فریم ==========
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

# ========== دریافت همه تایم‌فریم‌ها ==========
async def fetch_all_timeframes(session, symbol):
    settings = {"1m": 2, "5m": 7, "15m": 7, "30m": 14, "1h": 30, "4h": 60}
    tasks = [fetch_timeframe(session, symbol, tf, days) for tf, days in settings.items()]
    results = await asyncio.gather(*tasks)
    return {tf: candles for tf, candles in results if candles}

# ========== پردازش یک نماد - نسخه جدید با چک هر دو جهت ==========
async def process_symbol(symbol, data, index, total):
    if not data or "30m" not in data:
        logger.info(f"[{index}/{total}] {symbol} — ❌ داده کافی نیست")
        return

    closes_30 = [c['c'] for c in data["30m"]]
    ema21_30m = calculate_ema(closes_30, 21)
    ema55_30m = calculate_ema(closes_30, 55)
    ema8_30m = calculate_ema(closes_30, 8)  # اگر لازم است

    candle_1m = data.get("1m", [{}])[-1]
    open_1m = candle_1m.get("o")
    close_1m = candle_1m.get("c")
    high_1m = candle_1m.get("h")
    low_1m = candle_1m.get("l")

    candle_5m = data.get("5m", [{}])[-1]
    open_5m = candle_5m.get("o")
    close_5m = candle_5m.get("c")
    high_5m = candle_5m.get("h")
    low_5m = candle_5m.get("l")

    # EMAهای 1h و 4h
    closes_1h = [c['c'] for c in data.get("1h", [])]
    ema21_1h = calculate_ema(closes_1h, 21) if closes_1h else None
    ema55_1h = calculate_ema(closes_1h, 55) if closes_1h else None

    closes_4h = [c['c'] for c in data.get("4h", [])]
    ema21_4h = calculate_ema(closes_4h, 21) if closes_4h else None
    ema55_4h = calculate_ema(closes_4h, 55) if closes_4h else None
    ema200_4h = calculate_ema(closes_4h, 200) if closes_4h else None

    # محاسبه اندیکاتورهای مشترک (برای استفاده در هر دو جهت)
    macd_30m = calculate_macd(closes_30)
    rsi_30m = calculate_rsi(closes_30)
    atr_30m = calculate_atr(data["30m"]) if "30m" in data else None

    price_30m = closes_30[-1]

    # چک جهت LONG
    signal_long = await generate_signal(
        symbol=symbol,
        direction="LONG",
        prefer_risk="MEDIUM",
        price_30m=price_30m,
        open_15m=data.get("15m", [{}])[-1].get("o", price_30m),
        close_15m=data.get("15m", [{}])[-1].get("c", price_30m),
        high_15m=data.get("15m", [{}])[-1].get("h", price_30m),
        low_15m=data.get("15m", [{}])[-1].get("l", price_30m),
        open_5m=open_5m, close_5m=close_5m, high_5m=high_5m, low_5m=low_5m,
        open_1m=open_1m, close_1m=close_1m, high_1m=high_1m, low_1m=low_1m,
        ema21_30m=ema21_30m, ema55_30m=ema55_30m, ema8_30m=ema8_30m,
        ema21_1h=ema21_1h, ema55_1h=ema55_1h,
        ema21_4h=ema21_4h, ema55_4h=ema55_4h, ema200_4h=ema200_4h,
        macd_line_30m=macd_30m.get("macd") if macd_30m else None,
        hist_30m=macd_30m.get("histogram") if macd_30m else None,
        rsi_30m=rsi_30m,
        atr_val_30m=atr_30m or 0.0,
        curr_vol=data["30m"][-1].get("v", 0.0),
        avg_vol_30m=0.0,
        divergence_detected=False,
        candles=data["30m"],
        prices_series_30m=closes_30[-120:],
        closes_by_tf=data
    )

    # چک جهت SHORT
    signal_short = await generate_signal(
        symbol=symbol,
        direction="SHORT",
        prefer_risk="MEDIUM",
        price_30m=price_30m,
        open_15m=data.get("15m", [{}])[-1].get("o", price_30m),
        close_15m=data.get("15m", [{}])[-1].get("c", price_30m),
        high_15m=data.get("15m", [{}])[-1].get("h", price_30m),
        low_15m=data.get("15m", [{}])[-1].get("l", price_30m),
        open_5m=open_5m, close_5m=close_5m, high_5m=high_5m, low_5m=low_5m,
        open_1m=open_1m, close_1m=close_1m, high_1m=high_1m, low_1m=low_1m,
        ema21_30m=ema21_30m, ema55_30m=ema55_30m, ema8_30m=ema8_30m,
        ema21_1h=ema21_1h, ema55_1h=ema55_1h,
        ema21_4h=ema21_4h, ema55_4h=ema55_4h, ema200_4h=ema200_4h,
        macd_line_30m=macd_30m.get("macd") if macd_30m else None,
        hist_30m=macd_30m.get("histogram") if macd_30m else None,
        rsi_30m=rsi_30m,
        atr_val_30m=atr_30m or 0.0,
        curr_vol=data["30m"][-1].get("v", 0.0),
        avg_vol_30m=0.0,
        divergence_detected=False,
        candles=data["30m"],
        prices_series_30m=closes_30[-120:],
        closes_by_tf=data
    )

    # لاگ نتایج
    if signal_long and signal_long.get("status") == "SIGNAL":
        logger.info(f"✅ سیگنال LONG برای {symbol}: قیمت={signal_long['price']:.4f} | ریسک={signal_long.get('risk', 'نامشخص')}")

    if signal_short and signal_short.get("status") == "SIGNAL":
        logger.info(f"✅ سیگنال SHORT برای {symbol}: قیمت={signal_short['price']:.4f} | ریسک={signal_short.get('risk', 'نامشخص')}")

    if (not signal_long or signal_long.get("status") != "SIGNAL") and \
       (not signal_short or signal_short.get("status") != "SIGNAL"):
        logger.info(f"📭 بدون سیگنال معتبر برای {symbol} (نه LONG و نه SHORT)")

# ========== تابع اصلی ==========
async def main_async():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_all_timeframes(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*tasks)
        for idx, data in enumerate(results, 1):
            await process_symbol(SYMBOLS[idx-1], data, idx, len(SYMBOLS))

if __name__ == "__main__":
    asyncio.run(main_async())
