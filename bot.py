# bot.py
import requests
import time
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, RISK_LEVELS
from data_fetcher import fetch_all_timeframes
from indicators import calculate_rsi, calculate_ema, calculate_macd, body_strength
from rules import check_rules_for_level

# ========== ارسال سیگنال ==========
def send_signal(symbol, analysis_data, check_result, direction):
    clean_symbol = symbol.replace('-USDT','')
    dir_emoji = '🟢' if direction=='LONG' else '🔴'  # نوع معامله (لانگ/شورت)

    # حیوانات برای سطح ریسک
    if check_result['risk_name'] == 'ریسک کم':
        risk_symbol = '🦁'
    elif check_result['risk_name'] == 'ریسک میانی':
        risk_symbol = '🐺'
    else:
        risk_symbol = '🐒'

    last = analysis_data['last_close']
    stop = last*0.985 if direction=='LONG' else last*1.015
    target = last*1.03 if direction=='LONG' else last*0.97

    # پیام تلگرام با اعداد زیر هم
    msg = (
        f"{dir_emoji} {risk_symbol} {check_result['risk_name']} | {'لانگ' if direction=='LONG' else 'شورت'}\n"
        f"نماد: {clean_symbol}\n"
        f"قوانین گذرانده: {check_result['passed_count']}/9\n"
        f"دلایل: {', '.join(check_result['reasons'])}\n"
        f"ورود:\n{last:.2f}\n"
        f"استاپ:\n{stop:.2f}\n"
        f"تارگت:\n{target:.2f}\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload={"chat_id":TELEGRAM_CHAT_ID,"text":msg}
    try:
        r = requests.post(url,json=payload,timeout=15)
        if r.status_code == 200:
            print(f"✅ سیگنال {check_result['risk_name']} برای {symbol} ارسال شد")
        else:
            print(f"⚠️ ارسال تلگرام ناکام: {r.status_code} {r.text}")
    except Exception as e:
        print(f"❌ خطا در ارسال سیگنال: {e}")

# ========== پردازش نماد ==========
def process_symbol(symbol):
    data = fetch_all_timeframes(symbol)
    if not data:
        print(f"❌ دریافت داده ناموفق برای {symbol}")
        return

    closes = {tf: [c[2] for c in data[tf]] for tf in data}
    analysis = {'last_close': closes['5m'][-1], 'closes': closes, 'data': data}

    print(f"\n📊 گزارش کامل {symbol}:")
    print("-"*60)
    print(f"💰 قیمت فعلی: {analysis['last_close']:.2f}")

    # EMA
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            ema21 = calculate_ema(closes[tf],21)
            ema55 = calculate_ema(closes[tf],55)
            ema200 = calculate_ema(closes[tf],200) if len(closes[tf])>=200 else None
            ema21_str = f"{ema21:.2f}" if ema21 is not None else "N/A"
            ema55_str = f"{ema55:.2f}" if ema55 is not None else "N/A"
            ema200_str = f"{ema200:.2f}" if ema200 is not None else "N/A"
            print(f"  • {tf}: EMA21={ema21_str}, EMA55={ema55_str}, EMA200={ema200_str}")

    # RSI
    print("\n📊 RSI:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            rsi = calculate_rsi(closes[tf],14)
            rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
            print(f"  • {tf}: {rsi_str}")

    # MACD
    print("\n🌀 MACD:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            macd = calculate_macd(closes[tf])
            macd_str = f"{macd['macd']:.4f}" if macd['macd'] is not None else "N/A"
            signal_str = f"{macd['signal']:.4f}" if macd['signal'] is not None else "N/A"
            hist_str = f"{macd['histogram']:.4f}" if macd['histogram'] is not None else "N/A"
            print(f"  • {tf}: MACD={macd_str}, Signal={signal_str}, Hist={hist_str}")

    # قدرت کندل
    if '5m' in data:
        strength_5m = body_strength(data['5m'][-1])
        print(f"\n🕯️ قدرت کندل 5m: {strength_5m:.2f}")

    print("-"*60)

    # بررسی شرایط سیگنال
    print("\n🔎 بررسی شرایط سیگنال...")
    for direction in ['LONG','SHORT']:
        dir_text = "صعودی" if direction=='LONG' else "نزولی"
        print(f"\n➡️ بررسی جهت {dir_text}:")
        for risk in RISK_LEVELS:
            res = check_rules_for_level(analysis, risk, direction)
            print(f"   سطح {risk['name']} → قوانین گذرانده: {res['passed_count']}/9 | دلایل: {', '.join(res['reasons'])}")
            if res['passed']:
                print(f"   ✅ تصمیم: سیگنال {risk['name']} {dir_text}")
                send_signal(symbol, analysis, res, direction)
                return
    print("📭 هیچ سیگنال معتبری یافت نشد")

# ========== تابع اصلی ==========
def main():
    print("="*80)
    print("🚀 شروع تحلیل و سیگنال‌دهی")
    print(f"⏰ زمان شروع: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    for i, sym in enumerate(SYMBOLS,1):
        print(f"\n[{i}/{len(SYMBOLS)}] پردازش نماد {sym}")
        process_symbol(sym)
        if i < len(SYMBOLS): time.sleep(5)

    print("\n✅ پردازش کامل شد")
    print(f"⏰ پایان: {datetime.now().strftime('%H:%M:%S')}")
    print("="*80)

# ========== اجرا ==========
if __name__=="__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنظیمات تلگرام را بررسی کنید!")
    else:
        main()
