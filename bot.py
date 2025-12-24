import aiohttp
import asyncio
import time
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from rules import evaluate_rules, generate_signal

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, RISK_LEVELS, RISK_PARAMS
from indicators import (
    calculate_rsi, calculate_ema, calculate_macd, body_strength,
    swing_levels, calculate_atr
)
from signal_store import append_signal_row, compose_signal_source, tehran_time_str

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
                if not candles_raw:
                    return tf, []
                parsed = [
                    {'t': int(c[0]), 'o': float(c[1]), 'c': float(c[2]),
                     'h': float(c[3]), 'l': float(c[4]), 'v': float(c[5])}
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

# ========== دریافت همه تایم‌فریم‌ها ==========
async def fetch_all_timeframes(session, symbol):
    settings = {"5m": 7, "15m": 7, "30m": 14, "1h": 30, "4h": 60}
    tasks = [fetch_timeframe(session, symbol, tf, days) for tf, days in settings.items()]
    results = await asyncio.gather(*tasks)
    data = {}
    for tf, candles in results:
        if candles and len(candles) >= 50:
            data[tf] = candles
    return symbol, data if data else None

# ========== ارسال پیام به تلگرام ==========
async def send_to_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    async with aiohttp.ClientSession() as temp_session:
        try:
            async with temp_session.post(url, json=payload, timeout=15) as resp:
                if resp.status == 200:
                    logger.info("✅ پیام به تلگرام ارسال شد")
                else:
                    txt = await resp.text()
                    logger.warning(f"⚠️ خطا در ارسال تلگرام: {resp.status} {txt}")
        except Exception as e:
            logger.error(f"❌ خطا در ارسال به تلگرام: {e}")
            
# ========== پردازش یک نماد ==========
async def process_symbol(symbol, data, session, index, total):
    if not data:
        logger.info(f"\n[{index}/{total}] پردازش نماد {symbol} — ❌ داده دریافت نشد")
        return

    closes = {tf: [c['c'] for c in data[tf]] for tf in data}
    last_close = closes['5m'][-1] if '5m' in closes else 0.0

    logger.info(f"\n[{index}/{total}] پردازش نماد {symbol}")
    logger.info("=" * 80)
    logger.info(f"📊 گزارش اولیه {symbol}")
    logger.info(f"💰 قیمت فعلی (5m): {last_close:.4f}")
    logger.info("-" * 60)

    for tf, candles in data.items():
        last_candle = candles[-1]
        logger.info(f"⏱ تایم‌فریم {tf}: o={last_candle['o']:.4f}, c={last_candle['c']:.4f}, h={last_candle['h']:.4f}, l={last_candle['l']:.4f}, v={last_candle['v']:.2f}")

    results = []
    for direction in ['LONG', 'SHORT']:
        dir_text = "صعودی" if direction == 'LONG' else "نزولی"
        logger.info(f"\n➡️ بررسی جهت {dir_text}:")
        for risk in RISK_LEVELS:
            risk_key = risk["key"]       # LOW / MEDIUM / HIGH
            risk_name = risk["name"]     # نام فارسی
            risk_rules = risk["rules"]   # تنظیمات اختصاصی هر سطح

            # EMA و RSI خروجی float دارند
            ema21_30m = calculate_ema(closes['30m'], 21)
            ema8_30m = calculate_ema(closes['30m'], 8)
            ema55_30m = calculate_ema(closes['30m'], 55)
            ema21_1h = calculate_ema(closes['1h'], 21)
            ema55_1h = calculate_ema(closes['1h'], 55)
            ema21_4h = calculate_ema(closes['4h'], 21)
            ema55_4h = calculate_ema(closes['4h'], 55)

            # MACD می‌تواند dict یا tuple باشد
            macd_data = calculate_macd(closes['30m'])
            if isinstance(macd_data, tuple) and len(macd_data) == 3:
                _, _, hist = macd_data
                macd_hist_30m = hist[-1] if isinstance(hist, list) else hist
            elif isinstance(macd_data, dict):
                hist = macd_data.get("hist", [])
                macd_hist_30m = hist[-1] if isinstance(hist, list) and hist else hist
            else:
                macd_hist_30m = 0.0


            rsi_30m = calculate_rsi(closes['30m'])

            rule_results, passed_count = evaluate_rules(
                symbol=symbol,
                direction=direction,
                risk=risk_key,        # اینجا کلید رشته‌ای پاس داده می‌شود
                risk_rules=risk_rules, # ← اصلاح شد
                price_30m=last_close,
                open_15m=data['15m'][-1]['o'],
                close_15m=data['15m'][-1]['c'],
                high_15m=data['15m'][-1]['h'],
                low_15m=data['15m'][-1]['l'],
                ema21_30m=ema21_30m,
                ema8_30m=ema8_30m,
                ema21_1h=ema21_1h,
                ema55_1h=ema55_1h,
                ema21_4h=ema21_4h,
                ema55_4h=ema55_4h,
                macd_hist_30m=macd_hist_30m,
                rsi_30m=rsi_30m,
                vol_spike_factor=1.0,
                divergence_detected=False
            )

            res = {
                'passed': passed_count >= 5,
                'passed_count': passed_count,
                'passed_rules': [r.name for r in rule_results if r.passed],
                'reasons': [r.detail for r in rule_results],
                'risk_name': risk_name,
                'risk_key': risk_key,
                'direction': direction
            }

            logger.info(f"   سطح {risk_name} ({direction})")
            logger.info(f"      ✅ وضعیت: {'پاس شد' if res['passed'] else 'رد شد'}")
            logger.info(f"      📊 قوانین گذرانده: {res['passed_count']}/9")
            logger.info(f"      📋 لیست قوانین: {', '.join(res['passed_rules']) if res['passed_rules'] else 'هیچ‌کدام'}")
            logger.info(f"      📝 دلایل: {', '.join(res['reasons']) if res['reasons'] else '—'}")
            logger.info("-" * 60)

            if res['passed']:
                results.append(res)

    final = decide_signal(results)
    if final:
        logger.info(f"✅ تصمیم نهایی: {final['risk_name']} {final['direction']}")
        signal_obj = generate_signal(
            symbol=symbol,
            direction=final['direction'],
            prefer_risk=final['risk_key'],   # اینجا کلید رشته‌ای پاس داده می‌شود
            price_30m=last_close,
            open_15m=data['15m'][-1]['o'],
            close_15m=data['15m'][-1]['c'],
            high_15m=data['15m'][-1]['h'],
            low_15m=data['15m'][-1]['l'],
            ema21_30m=ema21_30m,
            ema55_30m=ema55_30m,
            ema8_30m=ema8_30m,
            ema21_1h=ema21_1h,
            ema55_1h=ema55_1h,
            ema21_4h=ema21_4h,
            ema55_4h=ema55_4h,
            macd_line_5m=0, hist_5m=0,
            macd_line_15m=0, hist_15m=0,
            macd_line_30m=0, hist_30m=macd_hist_30m,
            macd_line_1h=0, hist_1h=0,
            macd_line_4h=0, hist_4h=0,
            rsi_5m=calculate_rsi(closes['5m']),
            rsi_15m=calculate_rsi(closes['15m']),
            rsi_30m=rsi_30m,
            rsi_1h=calculate_rsi(closes['1h']),
            rsi_4h=calculate_rsi(closes['4h']),
            atr_val_30m=calculate_atr(data['30m']),
            curr_vol=data['30m'][-1]['v'],
            avg_vol_30m=sum([c['v'] for c in data['30m'][-20:]])/20,
            divergence_detected=False
        )
        if signal_obj:
            msg = compose_signal_source(signal_obj)
            await send_to_telegram(msg)
    else:
        logger.info("📭 هیچ سیگنال نهایی معتبر یافت نشد")



# ========== انتخاب نهایی سیگنال ==========
def decide_signal(results):
    if not results:
        return None

    scores = []
    for r in results:
        base = r['passed_count']
        weight = 3 if 'بالا' in r['risk_name'] else (2 if 'میانی' in r['risk_name'] else 1)
        score = base + weight
        scores.append((score, r))

    scores.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scores[0]

    if len(scores) > 1 and best_score - scores[1][0] < 1:
        for s, r in scores:
            if 'میانی' in r['risk_name']:
                return r
        return best

    return best


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
        tasks_fetch = [fetch_all_timeframes(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*tasks_fetch)

        tasks_process = [
            process_symbol(sym, data, session, idx, len(SYMBOLS))
            for idx, (sym, data) in enumerate(results, 1)
        ]
        await asyncio.gather(*tasks_process)

        for handler in logger.handlers:
            try:
                handler.flush()
            except Exception:
                pass

        duration = time.perf_counter() - start_time
        server_end = datetime.now()
        tehran_end = datetime.now(ZoneInfo("Asia/Tehran"))

        report = (
            "📊 گزارش اجرای ربات\n\n"
            f"تعداد ارزهای پردازش‌شده: {len([r for r in results if r[1]])}\n"
            f"مدت اجرا: {duration:.2f} ثانیه\n"
            f"پایان (تهران): {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await send_to_telegram(report)

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
