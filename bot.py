import aiohttp
import asyncio
import requests
import time
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

# ========== دریافت داده برای یک نماد ==========
async def fetch_all_timeframes(session, symbol, days=3):
    try:
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - days*24*3600

        tasks = []
        for tf, api_tf in intervals.items():
            params = {"symbol": symbol, "type": api_tf,
                      "startAt": start_time, "endAt": end_time}
            tasks.append(session.get(KUCOIN_URL, params=params, timeout=20))

        responses = await asyncio.gather(*tasks)
        result = {}
        for (tf, resp) in zip(intervals.keys(), responses):
            if resp.status == 200:
                data = await resp.json()
                candles = data.get("data", [])
                # شرط تعداد کندل‌ها برای تایم‌فریم‌های مختلف
                if tf == "4h":
                    min_required = 10
                else:
                    min_required = 50
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
    except Exception:
        return symbol, None
def process_symbol(symbol, data):
    if not data:
        print(f"❌ دریافت داده ناموفق برای {symbol}")
        return None

    closes = {tf: [c['c'] for c in data[tf]] for tf in data}
    analysis = {'last_close': closes['5m'][-1], 'closes': closes, 'data': data}

    print(f"\n📊 گزارش کامل {symbol}:")
    print("-"*60)
    print(f"💰 قیمت فعلی: {analysis['last_close']:.4f}")

    # EMA
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            ema21 = calculate_ema(closes[tf],21)
            ema55 = calculate_ema(closes[tf],55)
            ema200 = calculate_ema(closes[tf],200) if len(closes[tf])>=200 else None
            ema21_str = f"{ema21:.4f}" if ema21 is not None else "N/A"
            ema55_str = f"{ema55:.4f}" if ema55 is not None else "N/A"
            ema200_str = f"{ema200:.4f}" if ema200 is not None else "N/A"
            print(f"  • {tf}: EMA21={ema21_str}, EMA55={ema55_str}, EMA200={ema200_str}")

    # RSI
    print("\n📊 RSI:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            rsi_val = calculate_rsi(closes[tf],14)
            rsi_str = f"{rsi_val:.2f}" if rsi_val is not None else "N/A"
            print(f"  • {tf}: {rsi_str}")

    # MACD
    print("\n🌀 MACD:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            macd_obj = calculate_macd(closes[tf])
            macd_str = f"{macd_obj['macd']:.6f}" if macd_obj['macd'] is not None else "N/A"
            signal_str = f"{macd_obj['signal']:.6f}" if macd_obj['signal'] is not None else "N/A"
            hist_str = f"{macd_obj['histogram']:.6f}" if macd_obj['histogram'] is not None else "N/A"
            print(f"  • {tf}: MACD={macd_str}, Signal={signal_str}, Hist={hist_str}")

    # قدرت کندل
    if '5m' in data:
        strength_5m = body_strength(data['5m'][-1])
        print(f"\n🕯️ قدرت کندل 5m: {strength_5m:.2f}")

    print("-"*60)

    # بررسی شرایط سیگنال
    print("\n🔎 بررسی شرایط سیگنال...")
    any_signal = False
    for direction in ['LONG','SHORT']:
        dir_text = "صعودی" if direction=='LONG' else "نزولی"
        print(f"\n➡️ بررسی جهت {dir_text}:")
        for risk in RISK_LEVELS:
            res = check_rules_for_level(analysis, risk, direction)
            print(f"   سطح {risk['name']} → قوانین گذرانده: {res['passed_count']}/9 | دلایل: {', '.join(res['reasons'])}")
            if res['passed']:
                any_signal = True
                print(f"   ✅ تصمیم: سیگنال {risk['name']} {dir_text}")
                send_signal(symbol, analysis, res, direction)

    if not any_signal:
        print("📭 هیچ سیگنال معتبری یافت نشد")

    return True


# ========== تابع اصلی ==========
async def main_async():
    start_perf = time.perf_counter()
    server_start = datetime.now()
    tehran_start = datetime.now(ZoneInfo("Asia/Tehran"))

    print("="*80)
    print("🚀 شروع تحلیل و سیگنال‌دهی (async)")
    print(f"⏰ زمان شروع (سرور): {server_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏰ زمان شروع (تهران): {tehran_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    ok_symbols, fail_symbols = [], []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_all_timeframes(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*tasks)

    # پردازش نتایج
    for i, (sym, data) in enumerate(results, 1):
        print(f"\n[{i}/{len(SYMBOLS)}] پردازش نماد {sym}")
        if data:
            ok_symbols.append(sym)
            process_symbol(sym, data)
        else:
            fail_symbols.append(sym)
            print(f"❌ داده ناقص یا خطا برای {sym}")

    duration = time.perf_counter() - start_perf
    server_end = datetime.now()
    tehran_end = datetime.now(ZoneInfo("Asia/Tehran"))

    print("\n✅ پردازش کامل شد")
    print(f"⏰ پایان (سرور): {server_end.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏰ پایان (تهران): {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    # پیام جدید گزارش کلی
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
            print("✅ گزارش کلی به تلگرام ارسال شد")
        else:
            print(f"⚠️ ارسال گزارش کلی ناکام: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ خطا در ارسال گزارش کلی: {e}")

# ========== اجرا ==========
if __name__=="__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنظیمات تلگرام را بررسی کنید!")
    else:
        asyncio.run(main_async())
