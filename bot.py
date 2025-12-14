# bot.py
import requests
import time
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, RISK_LEVELS, RISK_PARAMS
from data_fetcher import fetch_all_timeframes
from indicators import (
    calculate_rsi, calculate_ema, calculate_macd, body_strength,
    swing_levels, calculate_atr
)
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

    # مدیریت ریسک دینامیک: اول ATR، اگر نبود از Swing
    atr_val = None
    if '15m' in analysis_data['data']:
        atr_val = calculate_atr(analysis_data['data']['15m'], period=14)

    if atr_val and atr_val > 0:
        k_stop = RISK_PARAMS.get('atr_multiplier', 1.2)
        rr = RISK_PARAMS.get('rr_target', 2.0)
        if direction == 'LONG':
            stop = last - k_stop * atr_val
            target = last + rr * (last - stop)
        else:
            stop = last + k_stop * atr_val
            target = last - rr * (stop - last)
        rr_calc = abs(target - last) / abs(last - stop) if stop != last else None
        risk_note = f"ATR14×{k_stop}, RR≈{rr_calc:.2f}" if rr_calc else f"ATR14×{k_stop}"
    else:
        # Swing-based fallback
        sh, sl = swing_levels(analysis_data['data']['5m'], lookback=RISK_PARAMS.get('swing_lookback', 10))
        if direction == 'LONG':
            stop = sl if sl is not None else last * 0.985
            target = last + RISK_PARAMS.get('rr_fallback', 2.0) * (last - stop)
        else:
            stop = sh if sh is not None else last * 1.015
            target = last - RISK_PARAMS.get('rr_fallback', 2.0) * (stop - last)
        rr_calc = abs(target - last) / abs(last - stop) if stop != last else None
        risk_note = f"Swing LR, RR≈{rr_calc:.2f}" if rr_calc else "Swing LR"

    # پیام تلگرام با اعداد زیر هم
    msg = (
        f"{dir_emoji} {risk_symbol} {check_result['risk_name']} | {'لانگ' if direction=='LONG' else 'شورت'}\n"
        f"نماد: {clean_symbol}\n"
        f"قوانین گذرانده: {check_result['passed_count']}/9\n"
        f"دلایل: {', '.join(check_result['reasons'])}\n"
        f"ورود:\n{last:.4f}\n"
        f"استاپ:\n{stop:.4f}\n"
        f"تارگت:\n{target:.4f}\n"
        f"مدیریت ریسک: {risk_note}\n"
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

    # MACD (نمایش آخرین مقدار—حالا دقیق‌تر چون سری کامل محاسبه می‌شود)
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
                # دیگر return نمی‌کنیم تا بقیه ارزها هم بررسی شوند

    if not any_signal:
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
        if i < len(SYMBOLS):
            time.sleep(10)   # فاصله بین پردازش هر ارز

    print("\n✅ پردازش کامل شد")
    print(f"⏰ پایان: {datetime.now().strftime('%H:%M:%S')}")
    print("="*80)

# ========== اجرا ==========
if __name__=="__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنظیمات تلگرام را بررسی کنید!")
    else:
        main()
