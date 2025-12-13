import requests
import time
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, RISK_LEVELS
from data_fetcher import fetch_all_timeframes
from indicators import calculate_rsi, calculate_ema, calculate_macd, body_strength
from rules import check_rules_for_level

def send_signal(symbol, analysis_data, check_result, direction):
    clean_symbol = symbol.replace('-USDT','')
    emoji = check_result['emoji']
    dir_emoji = '📈' if direction=='LONG' else '📉'
    last_close = analysis_data['last_close']
    stop = last_close*0.985 if direction=='LONG' else last_close*1.015
    target = last_close*1.03 if direction=='LONG' else last_close*0.97

    msg = f"""{emoji} سیگنال {check_result['risk_name']} {dir_emoji}
نماد: {clean_symbol}
قوانین گذرانده: {check_result['passed_count']}
دلایل: {', '.join(check_result['reasons'])}
ورود: {last_close:.2f} | استاپ: {stop:.2f} | تارگت: {target:.2f}
⏰ {datetime.now().strftime('%H:%M:%S')}"""

    url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload={"chat_id":TELEGRAM_CHAT_ID,"text":msg}
    try:
        r = requests.post(url,json=payload,timeout=15)
        if r.status_code == 200:
            print(f"✅ سیگنال {check_result['risk_name']} برای {symbol} ارسال شد")
    except Exception as e:
        print(f"❌ خطا در ارسال سیگنال: {e}")

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
            print(f"  • {tf}: EMA21={ema21:.2f if ema21 else 'N/A'}, EMA55={ema55:.2f if ema55 else 'N/A'}, EMA200={ema200:.2f if ema200 else 'N/A'}")

    # RSI
    print("\n📊 RSI:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            rsi = calculate_rsi(closes[tf],14)
            print(f"  • {tf}: {rsi:.1f if rsi else 'N/A'}")

    # MACD
    print("\n🌀 MACD:")
    for tf in ['5m','15m','30m','1h','4h']:
        if tf in closes:
            macd = calculate_macd(closes[tf])
            print(f"  • {tf}: MACD={macd['macd']:.4f if macd['macd'] else 'N/A'}, Signal={macd['signal']:.4f if macd['signal'] else 'N/A'}")

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
            print(f"   سطح {risk['emoji']} {risk['name']} → قوانین گذرانده: {res['passed_count']} | دلایل: {', '.join(res['reasons'])}")
            if res['passed']:
                print(f"   ✅ تصمیم: سیگنال {risk['name']} {dir_text}")
                send_signal(symbol, analysis, res, direction)
                return
    print("📭 هیچ سیگنال معتبری یافت نشد")

def main():
    print("="*80)
    print("🚀 شروع تحلیل و سیگنال‌دهی")
    print(f"⏰ زمان شروع: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

    for i, sym in enumerate(SYMBOLS,1):
        print(f"\n[{i}/{len(SYMBOLS)}] پردازش نماد {sym}")
        process_symbol(sym)
        if i < len(SYMBOLS):
            time.sleep(5)

    print("\n✅ پردازش کامل شد")
    print(f"⏰ پایان: {datetime.now().strftime('%H:%M:%S')}")
    print("="*80)

if __name__=="__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنظیمات تلگرام را بررسی کنید!")
    else:
        main()
