# bot.py
import aiohttp
import asyncio
import time
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, RISK_LEVELS, RISK_PARAMS
from indicators import (
    calculate_rsi, calculate_ema, calculate_macd, body_strength,
    swing_levels, calculate_atr
)
from rules import check_rules_for_level

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
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1hour",
    "4h": "4hour"
}

# ========== دریافت داده برای یک نماد ==========
async def fetch_timeframe(session, symbol, tf, days):
    api_tf = intervals[tf]
    end_time = int(datetime.utcnow().timestamp())
    start_time = end_time - days * 24 * 3600
    params = {
        "symbol": symbol,
        "type": api_tf,
        "startAt": start_time,
        "endAt": end_time
    }
    try:
        async with session.get(KUCOIN_URL, params=params, timeout=20) as resp:
            if resp.status == 200:
                data = await resp.json()
                candles_raw = data.get("data", [])
                if not candles_raw:
                    return tf, []
                parsed = [
                    {
                        't': int(c[0]),
                        'o': float(c[1]),
                        'c': float(c[2]),
                        'h': float(c[3]),
                        'l': float(c[4]),
                        'v': float(c[5])
                    }
                    for c in candles_raw
                ]
                return tf, list(reversed(parsed))
            elif resp.status == 429:
                logger.warning(f"Rate limit برای {symbol} {tf} — ۱۰ ثانیه صبر...")
                await asyncio.sleep(10)
                return await fetch_timeframe(session, symbol, tf, days)
            else:
                logger.warning(f"خطای HTTP {resp.status} برای {symbol} {tf}")
                return tf, []
    except Exception as e:
        logger.error(f"خطا در دریافت {symbol} {tf}: {e}")
        return tf, []

async def fetch_all_timeframes(session, symbol):
    tasks = []
    settings = {"5m": 7, "15m": 7, "30m": 14, "1h": 30, "4h": 60}
    for tf, days in settings.items():
        tasks.append(fetch_timeframe(session, symbol, tf, days))
    
    results = await asyncio.gather(*tasks)
    data = {}
    for tf, candles in results:
        if candles and len(candles) >= 50:
            data[tf] = candles
    return symbol, data if data else None

# ========== ارسال به تلگرام (async) ==========
async def send_to_telegram(session, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        async with session.post(url, json=payload, timeout=15) as resp:
            if resp.status == 200:
                logger.info("✅ پیام به تلگرام ارسال شد")
            else:
                txt = await resp.text()
                logger.warning(f"⚠️ خطا در ارسال تلگرام: {resp.status} {txt}")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال به تلگرام: {e}")

# ========== ارسال سیگنال ==========
async def send_signal(session, symbol, analysis_data, check_result, direction):
    clean_symbol = symbol.replace('-USDT', '')
    dir_emoji = '🟢' if direction == 'LONG' else '🔴'
    risk_symbol = '🦁' if 'کم' in check_result['risk_name'] else '🐺' if 'میانی' in check_result['risk_name'] else '🐒'

    last = analysis_data['last_close']

    # استاپ و تارگت دینامیک
    atr_val = calculate_atr(analysis_data['data'].get('15m', []), period=14) if '15m' in analysis_data['data'] else None
    if atr_val and atr_val > 0:
        mult = RISK_PARAMS.get('atr_multiplier', 1.2)
        rr = RISK_PARAMS.get('rr_target', 2.0)
        if direction == 'LONG':
            stop = last - mult * atr_val
            target = last + rr * (last - stop)
        else:
            stop = last + mult * atr_val
            target = last - rr * (stop - last)
    else:
        sh, sl = swing_levels(analysis_data['data'].get('5m', []), lookback=10)
        level = sl if direction == 'LONG' else sh
        stop = level or (last * 0.985 if direction == 'LONG' else last * 1.015)
        rr_fallback = RISK_PARAMS.get('rr_fallback', 2.0)
        target = last + rr_fallback * (last - stop) if direction == 'LONG' else last - rr_fallback * (stop - last)

    server_time = datetime.now()
    tehran_time = datetime.now(ZoneInfo("Asia/Tehran"))

    msg = (
        f"{dir_emoji} {risk_symbol} <b>{check_result['risk_name']}</b> | {'لانگ' if direction=='LONG' else 'شورت'}\n\n"
        f"نماد: <code>{clean_symbol}</code>\n"
        f"قوانین گذرانده: <b>{check_result['passed_count']}/9</b>\n"
        f"دلایل: {', '.join(check_result['reasons'])}\n\n"
        f"ورود: <code>{last:.4f}</code>\n"
        f"استاپ: <code>{stop:.4f}</code>\n"
        f"تارگت: <code>{target:.4f}</code>\n\n"
        f"⏰ سرور: {server_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏰ تهران: {tehran_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    await send_to_telegram(session, msg)

# ========== پردازش یک نماد ==========
def process_symbol(symbol, data, session):
    if not data:
        logger.error(f"❌ داده ناقص برای {symbol}")
        return

    closes = {tf: [c['c'] for c in data[tf]] for tf in data}
    analysis = {
        'last_close': closes['5m'][-1],
        'closes': closes,
        'data': data
    }

    logger.info(f"\n[پردازش] {symbol}")
    logger.info(f"قیمت فعلی: {analysis['last_close']:.4f}")

    # لاگ EMA, RSI, MACD (اختیاری — می‌تونی حذف کنی اگر زیاد باشه)
    # ...

    logger.info("\nبررسی سیگنال...")
    signal_sent = False
    for direction in ['LONG', 'SHORT']:
        dir_text = "لانگ" if direction == 'LONG' else "شورت"
        for risk in RISK_LEVELS:
            res = check_rules_for_level(analysis, risk, direction)
            logger.info(f"  {risk['name']} → {res['passed_count']}/9 | {', '.join(res['reasons'])}")
            if res['passed']:
                logger.info(f"  ✅ سیگنال {risk['name']} {dir_text}")
                asyncio.create_task(send_signal(session, symbol, analysis, res, direction))
                signal_sent = True

    if not signal_sent:
        logger.info("  هیچ سیگنالی صادر نشد")

# ========== تابع اصلی ==========
async def main_async():
    start_time = time.perf_counter()
    server_start = datetime.now()
    tehran_start = datetime.now(ZoneInfo("Asia/Tehran"))

    logger.info("=" * 80)
    logger.info("🚀 شروع تحلیل و سیگنال‌دهی (async)")
    logger.info(f"⏰ سرور: {server_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏰ تهران: {tehran_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_all_timeframes(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*tasks)

        for sym, data in results:
            process_symbol(sym, data, session)

    duration = time.perf_counter() - start_time
    server_end = datetime.now()
    tehran_end = datetime.now(ZoneInfo("Asia/Tehran"))

    logger.info("\n✅ پردازش کامل شد")
    logger.info(f"⏰ سرور: {server_end.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏰ تهران: {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏱ مدت اجرا: {duration:.2f} ثانیه")
    logger.info("=" * 80)

    # گزارش کلی به تلگرام
    report = (
        "📊 گزارش اجرای ربات\n\n"
        f"✅ ارزهای پردازش‌شده: {len([r for r in results if r[1]])}\n"
        f"❌ خطا/ناقص: {len([r for r in results if not r[1]])}\n"
        f"⏱ مدت اجرا: {duration:.2f} ثانیه\n"
        f"⏰ پایان (تهران): {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await send_to_telegram(session, report)

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ توکن یا چت آیدی تلگرام تنظیم نشده!")
    else:
        asyncio.run(main_async())
