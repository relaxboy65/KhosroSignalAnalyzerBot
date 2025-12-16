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
                if not candles_raw:
                    return tf, []
                parsed = [
                    {'t': int(c[0]), 'o': float(c[1]), 'c': float(c[2]),
                     'h': float(c[3]), 'l': float(c[4]), 'v': float(c[5])}
                    for c in candles_raw
                ]
                return tf, list(reversed(parsed))
            return tf, []
    except Exception as e:
        logger.error(f"خطا در {symbol} {tf}: {e}")
        return tf, []

async def fetch_all_timeframes(session, symbol):
    settings = {"5m": 7, "15m": 7, "30m": 14, "1h": 30, "4h": 60}
    tasks = [fetch_timeframe(session, symbol, tf, days) for tf, days in settings.items()]
    results = await asyncio.gather(*tasks)
    data = {}
    for tf, candles in results:
        if candles and len(candles) >= 50:
            data[tf] = candles
    return symbol, data if data else None

# ========== ارسال سیگنال ==========
async def send_signal(session, symbol, analysis_data, check_result, direction):
    clean_symbol = symbol.replace('-USDT', '')
    dir_emoji = '🟢' if direction == 'LONG' else '🔴'
    risk_symbol = '🦁' if 'کم' in check_result['risk_name'] else '🐺' if 'میانی' in check_result['risk_name'] else '🐒'

    last = analysis_data['last_close']

    # استاپ و تارگت
    atr_val = calculate_atr(analysis_data['data'].get('15m', []), period=14)
    if atr_val and atr_val > 0:
        mult = RISK_PARAMS.get('atr_multiplier', 1.2)
        rr = RISK_PARAMS.get('rr_target', 2.0)
        stop = last - mult * atr_val if direction == 'LONG' else last + mult * atr_val
        target = last + rr * (last - stop) if direction == 'LONG' else last - rr * (stop - last)
    else:
        sh, sl = swing_levels(analysis_data['data'].get('5m', []), lookback=10)
        level = sl if direction == 'LONG' else sh
        stop = level or (last * 0.985 if direction == 'LONG' else last * 1.015)
        target = last + RISK_PARAMS.get('rr_fallback', 2.0) * (last - stop) if direction == 'LONG' else last - RISK_PARAMS.get('rr_fallback', 2.0) * (stop - last)

    msg = (
        f"{dir_emoji} {risk_symbol} <b>{check_result['risk_name']}</b> | {'لانگ' if direction=='LONG' else 'شورت'}\n\n"
        f"نماد: <code>{clean_symbol}</code>\n"
        f"قوانین گذرانده: <b>{check_result['passed_count']}/9</b>\n"
        f"دلایل: {', '.join(check_result['reasons'])}\n\n"
        f"ورود: <code>{last:.4f}</code>\n"
        f"استاپ: <code>{stop:.4f}</code>\n"
        f"تارگت: <code>{target:.4f}</code>\n\n"
        f"⏰ {datetime.now(ZoneInfo('Asia/Tehran')).strftime('%Y-%m-%d %H:%M:%S')}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
    try:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                logger.info(f"✅ سیگنال {check_result['risk_name']} {direction} برای {symbol} ارسال شد")
            else:
                logger.warning(f"⚠️ خطا در ارسال سیگنال: {resp.status}")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال سیگنال: {e}")

# ========== پردازش یک نماد با خروجی دقیق ==========
def process_symbol(symbol, data, session):
    if not data:
        logger.info(f"\n[{symbol}] ❌ داده دریافت نشد")
        return

    closes = {tf: [c['c'] for c in data[tf]] for tf in data}
    last_close = closes['5m'][-1] if '5m' in closes else 0.0

    logger.info(f"\n[{symbol}] پردازش نماد {symbol}")
    logger.info("📊 گزارش کامل {symbol}:")
    logger.info("-" * 60)
    logger.info(f"💰 قیمت فعلی: {last_close:.4f}")

    # EMA
    logger.info("  • EMA:")
    for tf in ['5m', '15m', '30m', '1h', '4h']:
        if tf in closes:
            ema21 = calculate_ema(closes[tf], 21)
            ema55 = calculate_ema(closes[tf], 55)
            ema200 = calculate_ema(closes[tf], 200) if len(closes[tf]) >= 200 else "N/A"
            logger.info(f"    • {tf}: EMA21={ema21:.4f if ema21 else 'N/A'}, EMA55={ema55:.4f if ema55 else 'N/A'}, EMA200={ema200}")

    # RSI
    logger.info("\n📊 RSI:")
    for tf in ['5m', '15m', '30m', '1h', '4h']:
        if tf in closes:
            rsi_val = calculate_rsi(closes[tf], 14)
            logger.info(f"  • {tf}: {rsi_val:.2f if rsi_val else 'N/A'}")

    # MACD
    logger.info("\n🌀 MACD:")
    for tf in ['5m', '15m', '30m', '1h', '4h']:
        if tf in closes:
            macd_obj = calculate_macd(closes[tf])
            m, s, h = macd_obj['macd'], macd_obj['signal'], macd_obj['histogram']
            logger.info(f"  • {tf}: MACD={m:.6f if m else 'N/A'}, Signal={s:.6f if s else 'N/A'}, Hist={h:.6f if h else 'N/A'}")

    # قدرت کندل 5m
    if '5m' in data:
        strength_5m = body_strength(data['5m'][-1])
        logger.info(f"\n🕯️ قدرت کندل 5m: {strength_5m:.2f}")

    logger.info("-" * 60)

    # بررسی سیگنال
    logger.info("\n🔎 بررسی شرایط سیگنال...")
    any_signal = False
    analysis = {'last_close': last_close, 'closes': closes, 'data': data}

    for direction in ['LONG', 'SHORT']:
        dir_text = "صعودی" if direction == 'LONG' else "نزولی"
        logger.info(f"\n➡️ بررسی جهت {dir_text}:")
        for risk in RISK_LEVELS:
            res = check_rules_for_level(analysis, risk, direction)
            reasons_text = ', '.join(res['reasons']) if res['reasons'] else ''
            logger.info(f"   سطح {risk['name']} → قوانین گذرانده: {res['passed_count']}/9 | دلایل: {reasons_text}")
            if res['passed']:
                any_signal = True
                logger.info(f"   ✅ تصمیم: سیگنال {risk['name']} {dir_text}")
                asyncio.create_task(send_signal(session, symbol, analysis, res, direction))

    if not any_signal:
        logger.info("📭 هیچ سیگنال معتبری یافت نشد")

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

        idx = 1
        for sym, data in results:
            logger.info(f"\n[{idx}/{len(SYMBOLS)}] پردازش نماد {sym}")
            process_symbol(sym, data, session)
            idx += 1

    duration = time.perf_counter() - start_time
    server_end = datetime.now()
    tehran_end = datetime.now(ZoneInfo("Asia/Tehran"))

    logger.info("\n✅ پردازش کامل شد")
    logger.info(f"⏰ سرور: {server_end.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏰ تهران: {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏱ مدت اجرا: {duration:.2f} ثانیه")
    logger.info("=" * 80)

if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ تنظیمات تلگرام را بررسی کنید!")
    else:
        asyncio.run(main_async())
