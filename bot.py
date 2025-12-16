import aiohttp
import asyncio
import requests
import time
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo   # پایتون 3.9+

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, RISK_LEVELS, RISK_PARAMS
from indicators import (
    calculate_rsi, calculate_ema, calculate_macd, body_strength,
    swing_levels, calculate_atr
)
from rules import check_rules_for_level

KUCOIN_URL = "https://api.kucoin.com/api/v1/market/candles"

intervals = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1hour",
    "4h": "4hour"
}

# ========== تنظیمات لاگ ==========
logger = logging.getLogger()
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

file_handler = logging.FileHandler("bot_log.txt", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# ========== دریافت داده برای یک نماد ==========
async def fetch_all_timeframes(session, symbol):
    try:
        end_time = int(datetime.utcnow().timestamp())
        result = {}

        for tf, api_tf in intervals.items():
            # بازه‌ی زمانی متفاوت برای هر تایم‌فریم
            if tf == "4h":
                start_time = end_time - 40*24*3600
                min_required = 10
            elif tf == "1h":
                start_time = end_time - 14*24*3600
                min_required = 50
            else:
                start_time = end_time - 7*24*3600
                min_required = 50

            params = {"symbol": symbol, "type": api_tf,
                      "startAt": start_time, "endAt": end_time}
            async with session.get(KUCOIN_URL, params=params, timeout=20) as resp:
                await asyncio.sleep(0.5)
                if resp.status == 200:
                    data = await resp.json()
                    candles = data.get("data", [])
                    if candles and len(candles) >= min_required:
                        parsed = [
                            {
                                't': int(c[0]),
                                'o': float(c[1]),
                                'c': float(c[2]),
                                'h': float(c[3]),
                                'l': float(c[4]),
                                'v': float(c[5])
                            }
                            for c in candles
                        ]
                        result[tf] = parsed
        return symbol, result if result else None
    except Exception as e:
        logger.error(f"❌ خطا در دریافت داده برای {symbol}: {e}")
        return symbol, None


# ========== ارسال سیگنال ==========
def send_signal(symbol, analysis_data, check_result, direction):
    clean_symbol = symbol.replace('-USDT','')
    dir_emoji = '🟢' if direction=='LONG' else '🔴'
    risk_symbol = '🦁' if check_result['risk_name']=='ریسک کم' else '🐺' if check_result['risk_name']=='ریسک میانی' else '🐒'

    last = analysis_data['last_close']
    atr_val = calculate_atr(analysis_data['data']['15m'], period=14)

    if atr_val:
        stop = last - RISK_PARAMS['atr_multiplier']*atr_val if direction=='LONG' else last + RISK_PARAMS['atr_multiplier']*atr_val
        target = last + RISK_PARAMS['rr_target']*(last-stop) if direction=='LONG' else last - RISK_PARAMS['rr_target']*(stop-last)
    else:
        sh, sl = swing_levels(analysis_data['data']['5m'])
        stop = sl if direction=='LONG' else sh
        target = last + RISK_PARAMS['rr_fallback']*(last-stop) if direction=='LONG' else last - RISK_PARAMS['rr_fallback']*(stop-last)

    server_time = datetime.now()
    tehran_time = datetime.now(ZoneInfo("Asia/Tehran"))

    msg = (
        f"{dir_emoji} {risk_symbol} {check_result['risk_name']} | {'لانگ' if direction=='LONG' else 'شورت'}\n"
        f"نماد: {clean_symbol}\n"
        f"قوانین گذرانده: {check_result['passed_count']}/9\n"
        f"دلایل: {', '.join(check_result['reasons'])}\n"
        f"ورود:\n{last:.4f}\n"
        f"استاپ:\n{stop:.4f}\n"
        f"تارگت:\n{target:.4f}\n"
        f"⏰ زمان سرور: {server_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏰ زمان تهران: {tehran_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload={"chat_id":TELEGRAM_CHAT_ID,"text":msg}
    try:
        r = requests.post(url,json=payload,timeout=15)
        if r.status_code == 200:
            logger.info(f"✅ سیگنال {check_result['risk_name']} برای {symbol} ارسال شد")
        else:
            logger.warning(f"⚠️ ارسال تلگرام ناکام: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال سیگنال: {e}")
def process_symbol(symbol, data):
    if not data:
        logger.error(f"❌ دریافت داده ناموفق برای {symbol}")
        return None

    closes = {tf: [c['c'] for c in data[tf]] for tf in data}
    analysis = {'last_close': closes['5m'][-1], 'closes': closes, 'data': data}

    logger.info(f"\n📊 گزارش کامل {symbol}:")
    logger.info("-"*60)
    logger.info(f"💰 قیمت فعلی: {analysis['last_close']:.4f}")

    # EMA
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            ema21 = calculate_ema(closes[tf],21)
            ema55 = calculate_ema(closes[tf],55)
            ema200 = calculate_ema(closes[tf],200) if len(closes[tf])>=200 else None
            logger.info(f"  • {tf}: EMA21={ema21}, EMA55={ema55}, EMA200={ema200}")

    # RSI
    logger.info("\n📊 RSI:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            rsi_val = calculate_rsi(closes[tf],14)
            logger.info(f"  • {tf}: {rsi_val}")

    # MACD
    logger.info("\n🌀 MACD:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            macd_obj = calculate_macd(closes[tf])
            logger.info(f"  • {tf}: MACD={macd_obj['macd']}, Signal={macd_obj['signal']}, Hist={macd_obj['histogram']}")

    # قدرت کندل
    if '5m' in data:
        strength_5m = body_strength(data['5m'][-1])
        logger.info(f"\n🕯️ قدرت کندل 5m: {strength_5m:.2f}")

    logger.info("-"*60)

    # بررسی شرایط سیگنال
    logger.info("\n🔎 بررسی شرایط سیگنال...")
    any_signal = False
    for direction in ['LONG','SHORT']:
        dir_text = "صعودی" if direction=='LONG' else "نزولی"
        logger.info(f"\n➡️ بررسی جهت {dir_text}:")
        for risk in RISK_LEVELS:
            res = check_rules_for_level(analysis, risk, direction)
            logger.info(f"   سطح {risk['name']} → قوانین گذرانده: {res['passed_count']}/9 | دلایل: {', '.join(res['reasons'])}")
            if res['passed']:
                any_signal = True
                logger.info(f"   ✅ تصمیم: سیگنال {risk['name']} {dir_text}")
                send_signal(symbol, analysis, res, direction)

    if not any_signal:
        logger.info("📭 هیچ سیگنال معتبری یافت نشد")

    return True


# ========== تابع اصلی ==========
async def main_async():
    start_perf = time.perf_counter()
    server_start = datetime.now()
    tehran_start = datetime.now(ZoneInfo("Asia/Tehran"))

    logger.info("="*80)
    logger.info("🚀 شروع تحلیل و سیگنال‌دهی (async)")
    logger.info(f"⏰ زمان شروع (سرور): {server_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏰ زمان شروع (تهران): {tehran_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)

    ok_symbols, fail_symbols = [], []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_all_timeframes(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*tasks)

    # پردازش نتایج
    for i, (sym, data) in enumerate(results, 1):
        logger.info(f"\n[{i}/{len(SYMBOLS)}] پردازش نماد {sym}")
        if data:
            ok_symbols.append(sym)
            process_symbol(sym, data)
        else:
            fail_symbols.append(sym)
            logger.error(f"❌ داده ناقص یا خطا برای {sym}")

    duration = time.perf_counter() - start_perf
    server_end = datetime.now()
    tehran_end = datetime.now(ZoneInfo("Asia/Tehran"))

    logger.info("\n✅ پردازش کامل شد")
    logger.info(f"⏰ پایان (سرور): {server_end.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏰ پایان (تهران): {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)

    # پیام گزارش کلی
    report_msg = (
        "📊 گزارش اجرای ربات\n"
        f"✅ ارزهای کامل: {', '.join(ok_symbols) if ok_symbols else 'هیچکدام'}\n"
        f"❌ ارزهای ناقص: {', '.join(fail_symbols) if fail_symbols else 'هیچکدام'}\n"
        f"⏱ مدت اجرا: {duration:.2f} ثانیه\n"
        f"⏰ پایان (سرور): {server_end.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏰ پایان (تهران): {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload={"chat_id":TELEGRAM_CHAT_ID,"text":report_msg}
    try:
        r = requests.post(url,json=payload,timeout=15)
        if r.status_code == 200:
            logger.info("✅ گزارش کلی به تلگرام ارسال شد")
        else:
            logger.warning(f"⚠️ ارسال گزارش کلی ناکام: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"❌ خطا در ارسال گزارش کلی: {e}")


# ========== اجرا ==========
if __name__=="__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ تنظیمات تلگرام را بررسی کنید!")
    else:
        asyncio.run(main_async())
