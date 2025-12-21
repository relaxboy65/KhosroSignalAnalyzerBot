from indicators import (
    calculate_ema,
    body_strength,
    rsi_count_ok,
    macd_count_ok,
    no_divergence
)
import numpy as np

# =========================================================
# Helper: استخراج قیمت‌ها از کندل (سازگار با dict و list)
# =========================================================
def get_prices(candle):
    if isinstance(candle, dict):
        o = candle.get('open') or candle.get('قیمت باز') or candle.get('o')
        h = candle.get('high') or candle.get('سقف') or candle.get('h')
        l = candle.get('low') or candle.get('کف') or candle.get('l')
        c = candle.get('close') or candle.get('قیمت پایانی') or candle.get('c')
        v = candle.get('volume') or candle.get('حجم') or candle.get('v')
        return o, h, l, c, v
    elif isinstance(candle, (list, tuple)) and len(candle) >= 5:
        return candle[0], candle[1], candle[2], candle[3], candle[4]
    else:
        return None, None, None, None, None


# =========================================================
# Helper: ساختار روند با تحمل خطا
# =========================================================
def structure_with_tolerance(candles, count, direction, tolerance=0.002):
    if not candles or len(candles) < count:
        return False
    try:
        highs, lows = [], []
        for c in candles[-count:]:
            o, h, l, cl, v = get_prices(c)
            if h is None or l is None:
                return False
            highs.append(h)
            lows.append(l)
    except Exception:
        return False

    if direction == 'LONG':
        for i in range(1, count):
            if highs[i] < highs[i-1] * (1 - tolerance):
                return False
            if lows[i] < lows[i-1] * (1 - tolerance):
                return False
        return True

    if direction == 'SHORT':
        for i in range(1, count):
            if highs[i] > highs[i-1] * (1 + tolerance):
                return False
            if lows[i] > lows[i-1] * (1 + tolerance):
                return False
        return True

    return False

# =========================================================
# Helper: رنج سالم در 4h
# =========================================================
def is_healthy_range(candles, lookback=10, max_range_percent=0.008):
    if not candles or len(candles) < lookback:
        return False
    try:
        highs, lows = [], []
        for c in candles[-lookback:]:
            o, h, l, cl, v = get_prices(c)
            if h is None or l is None:
                return False
            highs.append(h)
            lows.append(l)
    except Exception:
        return False

    high = max(highs)
    low = min(lows)
    if low <= 0:
        return False

    range_percent = (high - low) / low
    return range_percent <= max_range_percent

# =========================================================
# Helper: بررسی قدرت واقعی ورود
# =========================================================
def has_real_entry_power(data_15m, direction):
    if not data_15m or len(data_15m) < 3:
        return False, "داده 15m ناکافی"
    
    current_candle = data_15m[-1]
    prev_candle = data_15m[-2]

    o_cur, h_cur, l_cur, c_cur, v_cur = get_prices(current_candle)
    o_prev, h_prev, l_prev, c_prev, v_prev = get_prices(prev_candle)

    if o_cur is None or c_cur is None or o_prev is None or c_prev is None:
        return False, "ساختار کندل نامعتبر"

    bs_current = body_strength(current_candle)
    bs_prev = body_strength(prev_candle)

    if bs_current < 0.4:
        return False, f"کندل فعلی ضعیف: {bs_current:.2f}"

    if direction == 'LONG' and c_prev < o_prev:
        if bs_prev > 0.4:
            return False, "کندل قبلی نزولی قوی"
    elif direction == 'SHORT' and c_prev > o_prev:
        if bs_prev > 0.4:
            return False, "کندل قبلی صعودی قوی"

    return True, "قدرت ورود مناسب"

# =========================================================
# Helper: بررسی فاصله داینامیک EMA21
# =========================================================
def check_ema_distance_dynamic(last_close, ema21, atr_percent):
    if atr_percent < 0.005: min_distance = 0.001
    elif atr_percent < 0.015: min_distance = 0.002
    else: min_distance = 0.003
    price_vs_ema = abs(last_close - ema21) / ema21
    return price_vs_ema >= min_distance, price_vs_ema, min_distance

# =========================================================
# Helper: بررسی شیب EMA21
# =========================================================
def check_ema_slope(closes_30m, period=21, lookback_candles=5):
    if len(closes_30m) < period + lookback_candles:
        return None, "داده ناکافی"
    ema_current = calculate_ema(closes_30m, period)
    ema_past = calculate_ema(closes_30m[:-lookback_candles], period)
    if ema_past == 0: return None, "EMA گذشته صفر"
    slope = (ema_current - ema_past) / ema_past
    slope_percent = slope * 100
    min_slope_percent = 0.1 if lookback_candles == 5 else 0.2
    return {
        'slope': slope, 'slope_percent': slope_percent,
        'min_required': min_slope_percent,
        'passed': abs(slope_percent) >= min_slope_percent,
        'direction': 'up' if slope > 0 else 'down' if slope < 0 else 'flat'
    }, None

# =========================================================
# Helper: بررسی قدرت MACD
# =========================================================
def check_macd_strength_dynamic(macd_vals, direction, risk_level, symbol_volatility):
    strong_count = very_strong_count = total_strength = 0
    strongest_tf, strongest_value = None, 0
    threshold = 0.3 if symbol_volatility < 0.01 else 0.5 if symbol_volatility < 0.03 else 0.8
    weights = {'5m':0.5,'15m':1.0,'30m':1.5,'1h':2.0,'4h':1.0}
    for tf,(macd_line,hist) in macd_vals.items():
        w = weights.get(tf,1.0)
        if (direction=='LONG' and hist>0) or (direction=='SHORT' and hist<0):
            strong_count += 1
            s = abs(hist)*w; total_strength += s
            if s>threshold: very_strong_count += 1
            if s>strongest_value: strongest_value, strongest_tf = s, tf
    min_strong,min_total,min_very = (3,2.0,1) if risk_level=="ریسک میانی" else (2,1.0,0)
    passed = strong_count>=min_strong and total_strength>=min_total and very_strong_count>=min_very
    return passed, {'strong_count':strong_count,'very_strong_count':very_strong_count,
                    'total_strength':round(total_strength,2),
                    'strongest':f"{strongest_tf}({strongest_value:.2f})" if strongest_tf else "ندارد",
                    'passed':passed}

# =========================================================
# Helper: بررسی RSI اشباع شدید
# =========================================================
def check_rsi_extreme(rsi_vals, direction, risk_level):
    crit={'5m':{'LONG':85,'SHORT':15},'15m':{'LONG':82,'SHORT':18},'30m':{'LONG':80,'SHORT':20},
          '1h':{'LONG':78,'SHORT':22},'4h':{'LONG':75,'SHORT':25}}
    warn={'5m':{'LONG':80,'SHORT':20},'15m':{'LONG':78,'SHORT':22},'30m':{'LONG':75,'SHORT':25},
          '1h':{'LONG':72,'SHORT':28},'4h':{'LONG':70,'SHORT':30}}
    for tf,val in rsi_vals.items():
        if tf not in crit: continue
        if direction=='LONG':
            if val>=crit[tf]['LONG']: return False,f"RSI {tf} بحرانی: {val:.1f}"
            if val>=warn[tf]['LONG'] and risk_level=="ریسک میانی": return False,f"RSI {tf} بالا: {val:.1f}"
        else:
            if val<=crit[tf]['SHORT']: return False,f"RSI {tf} بحرانی: {val:.1f}"
            if val<=warn[tf]['SHORT'] and risk_level=="ریسک میانی": return False,f"RSI {tf} پایین: {val:.1f}"
    return True,"RSI قابل قبول"

# =========================================================
# Helper: بررسی حمایت/مقاومت
# =========================================================
def check_support_resistance_dynamic(data_4h, current_price, direction, symbol=""):
    if not data_4h or len(data_4h)<20: return True,"داده ناکافی"
    highs=[get_prices(c)[1] for c in data_4h[-20:]]
    lows=[get_prices(c)[2] for c in data_4h[-20:]]
    vol=(max(highs)-min(lows))/((max(highs)+min(lows))/2)
    min_dist=0.008 if vol<0.02 else 0.012 if vol<0.05 else 0.02
    custom={'BTC-USDT':0.006,'ETH-USDT':0.007,'XAUT-USDT':0.005,'SOL-USDT':0.015}
    if symbol in custom: min_dist=custom[symbol]
    res=min([h for h in highs if h>current_price],default=None)
    sup=max([l for l in lows if l<current_price],default=None)
    if direction=='LONG' and res:
        if (res-current_price)/current_price<min_dist: return False,f"نزدیک مقاومت"
    if direction=='SHORT' and sup:
        if (current_price-sup)/current_price<min_dist: return False,f"نزدیک حمایت"
    return True,"فاصله مناسب"

# =========================================================
# Helper: محاسبه نوسان نماد
# =========================================================
def calculate_symbol_volatility(data_30m):
    if not data_30m or len(data_30m)<20: return 0.02
    highs=[get_prices(c)[1] for c in data_30m[-20:]]
    lows=[get_prices(c)[2] for c in data_30m[-20:]]
    avg=(sum(highs)+sum(lows))/(len(highs)+len(lows))
    if avg>0: return max(0.005,min((max(highs)-min(lows))/avg,0.1))
    return 0.02

# =========================================================
# Helper: بررسی حجم معاملات
# =========================================================
def check_volume_dynamic(current_volume, avg_volume, symbol_volatility, timeframe='15m'):
    if avg_volume<=0: return True,"حجم میانگین نامعتبر",1.0
    ratio=current_volume/avg_volume
    min_ratio=1.4 if symbol_volatility<0.01 else 1.6 if symbol_volatility<0.03 else 1.8
    if timeframe=='5m': min_ratio*=1.2
    elif timeframe=='1h': min_ratio*=0.9
    if ratio>=min_ratio: return True,f"حجم مناسب ({ratio:.1f}x)",ratio
    else: return False,f"حجم ناکافی ({ratio:.1f}x<{min_ratio:.1f}x)",ratio
# =========================================================
# MAIN RULES: ULTIMATE TP MAXIMIZER v5
# =========================================================
def check_rules_ultimate_tp_maximizer(analysis_data, direction):
    last_close = analysis_data.get('last_close')
    closes = analysis_data.get('closes', {})
    data = analysis_data.get('data', {})

    passed_rules = []
    reasons = []
    risk_name = "ریسک میانی"
    symbol = analysis_data.get('symbol', '')

    # 🔹 اضافه کن: محاسبه نوسان نماد
    symbol_volatility = calculate_symbol_volatility(data.get('30m', []))


    # --- Rule 1: قدرت واقعی ورود ---
    entry_power_ok, entry_msg = has_real_entry_power(data['15m'], direction)
    if not entry_power_ok:
        return fail(entry_msg)
    passed_rules.append("قدرت ورود")

    # --- Rule 2: روند 1h ---
    if '1h' not in data or not structure_with_tolerance(data['1h'], 3, direction, tolerance=0.002):
        if len(data['1h']) >= 2:
            last_candle = data['1h'][-1]
            prev_candle = data['1h'][-2]
            o_last, h_last, l_last, c_last, _ = get_prices(last_candle)
            o_prev, h_prev, l_prev, c_prev, _ = get_prices(prev_candle)
            bs1 = body_strength(last_candle)
            bs2 = body_strength(prev_candle)
            if direction == 'LONG' and c_last > o_last and c_prev > o_prev:
                if bs1 > 0.4 and bs2 > 0.4:
                    passed_rules.append("دو کندل 1h قوی")
                else:
                    return fail("روند 1h ضعیف")
            elif direction == 'SHORT' and c_last < o_last and c_prev < o_prev:
                if bs1 > 0.4 and bs2 > 0.4:
                    passed_rules.append("دو کندل 1h قوی")
                else:
                    return fail("روند 1h ضعیف")
            else:
                return fail("روند 1h برقرار نیست")
        else:
            return fail("روند 1h برقرار نیست")
    else:
        passed_rules.append("روند 1h معتبر")

    # --- Rule 3: کانتکست 4h ---
    trend_4h = structure_with_tolerance(data.get('4h', []), 4, direction, tolerance=0.003)
    range_4h = is_healthy_range(data.get('4h', []), max_range_percent=0.01)
    if not (trend_4h or range_4h):
        strong_1h = structure_with_tolerance(data['1h'], 4, direction, tolerance=0.0015)
        if strong_1h:
            risk_name = "ریسک بالا"
            reasons.append("1h بسیار قوی (فال‌بک)")
            passed_rules.append("فال‌بک: 1h قوی")
        else:
            return fail("کانتکست 4h نامعتبر")
    else:
        if trend_4h:
            passed_rules.append("روند 4h")
        elif range_4h:
            passed_rules.append("رنج سالم 4h")

    # --- Rule 4: کندل تصمیم (BS15) ---
    bs15 = body_strength(data['15m'][-1])
    if risk_name == "ریسک میانی":
        if bs15 < 0.5:
            return fail(f"کندل 15m ضعیف: {bs15:.2f}")
    else:
        if bs15 < 0.5:
            return fail(f"کندل 15m ضعیف: {bs15:.2f}")
    passed_rules.append(f"کندل قوی ({bs15:.2f})")

    # --- Rule 5: RSI ---
    rsi_ok, rsi_count, rsi_vals = rsi_count_ok(closes, direction, required=3)
    if not rsi_ok:
        return fail(f"RSI هم‌جهت کافی نیست: {rsi_count}/5")
    rsi_extreme_ok, rsi_extreme_msg = check_rsi_extreme(rsi_vals, direction, risk_name)
    if not rsi_extreme_ok:
        return fail(rsi_extreme_msg)
    passed_rules.append(f"RSI ({rsi_count}/5)")

    # --- Rule 6: MACD ---
    macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, required=3)
    if not macd_ok:
        return fail(f"MACD هم‌جهت کافی نیست: {macd_count}/5")
    macd_strength_ok, macd_summary = check_macd_strength_dynamic(macd_vals, direction, risk_name, symbol_volatility)
    if not macd_strength_ok:
        return fail("MACD قدرت کافی ندارد")
    reasons.append(f"MACD: {macd_summary['strong_count']}/5 همسو | قدرت: {macd_summary['total_strength']}")
    passed_rules.append("MACD قوی")

    # --- Rule 7: عدم واگرایی ---
    if not no_divergence(data, closes):
        return fail("واگرایی مشاهده شد")
    passed_rules.append("بدون واگرایی")

    # --- Rule 8: فاصله از سطوح کلیدی ---
    if '4h' in data:
        sr_ok, sr_msg = check_support_resistance_dynamic(data['4h'], last_close, direction, symbol)
        if not sr_ok:
            if risk_name == "ریسک بالا":
                reasons.append(f"{sr_msg} (با ریسک بالا)")
            else:
                return fail(sr_msg)
        else:
            passed_rules.append("فاصله سطوح")

    # --- Rule 9: EMA21 فاصله و شیب ---
    if '30m' in closes and len(closes['30m']) >= 26:
        ema21 = calculate_ema(closes['30m'], 21)
        if ema21 is not None:
            recent_prices = closes['30m'][-14:]
            if len(recent_prices) >= 10:
                price_range = max(recent_prices) - min(recent_prices)
                avg_price = np.mean(recent_prices)
                atr_simple = price_range / avg_price if avg_price > 0 else 0.01
                ema_ok, ema_distance, min_req = check_ema_distance_dynamic(last_close, ema21, atr_simple)
                if not ema_ok:
                    reasons.append(f"فاصله EMA: {ema_distance:.3%}")
                ema_slope_info, slope_error = check_ema_slope(closes['30m'], period=21, lookback_candles=5)
                if ema_slope_info and ema_slope_info['passed']:
                    passed_rules.append(f"شیب EMA ({ema_slope_info['direction']})")

    # --- Rule 10: حجم معاملات ---
    if 'volume' in analysis_data and len(analysis_data['volume']) >= 10:
        recent_vol = analysis_data['volume'][-10:]
        avg_vol = sum(recent_vol[-5:]) / 5
        current_vol = recent_vol[-1] if recent_vol else 0
        volume_ok, volume_msg, volume_ratio = check_volume_dynamic(current_vol, avg_vol, symbol_volatility, '15m')
        if volume_ok:
            passed_rules.append("حجم مناسب")
            reasons.append(f"حجم: {volume_ratio:.1f}x")
        else:
            reasons.append(volume_msg)

    return {
        'passed': True,
        'passed_rules': passed_rules,
        'passed_count': len(passed_rules),
        'reasons': reasons,
        'risk_name': risk_name,
        'bs15': bs15,
        'rsi_count': rsi_count,
        'macd_summary': macd_summary
    }
    

# =========================================================
# Fail helper
# =========================================================
def fail(reason):
    return {
        'passed': False,
        'passed_rules': [],
        'passed_count': 0,
        'reasons': [reason],
        'risk_name': 'ULTIMATE TP MAXIMIZER v5'
    }

# =========================================================
# Wrapper برای سازگاری با bot.py
# =========================================================
def check_rules_for_level(analysis_data, risk, direction):
    return check_rules_ultimate_tp_maximizer(analysis_data, direction)


async def send_signal(symbol, analysis_data, check_result, direction):
    clean_symbol = symbol.replace('-USDT', '')
    dir_emoji = '🟢' if direction == 'LONG' else '🔴'
    risk_symbol = '🦁' if 'کم' in check_result['risk_name'] else '🐺' if 'میانی' in check_result['risk_name'] else '🐒'

    last = analysis_data['last_close']

    # محاسبه استاپ و تارگت دینامیک
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
        if direction == 'LONG':
            target = last + RISK_PARAMS.get('rr_fallback', 2.0) * (last - stop)
        else:
            target = last - RISK_PARAMS.get('rr_fallback', 2.0) * (stop - last)

    tehran_time = datetime.now(ZoneInfo("Asia/Tehran"))

    # پیام تلگرام (همان استایل فعلی)
    msg = (
        f"{dir_emoji} {risk_symbol} <b>{check_result['risk_name']}</b> | {'لانگ' if direction=='LONG' else 'شورت'}\n\n"
        f"نماد: <code>{clean_symbol}</code>\n"
        f"قوانین گذرانده: <b>{check_result['passed_count']}/9</b>\n"
        f"دلایل: {', '.join(check_result['reasons']) if check_result['reasons'] else '—'}\n\n"
        f"ورود: <code>{last:.4f}</code>\n"
        f"استاپ: <code>{stop:.4f}</code>\n"
        f"تارگت: <code>{target:.4f}</code>\n\n"
        f"⏰ {tehran_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await send_to_telegram(msg)

    # ذخیره در CSV روزانه
    issued_at_tehran = tehran_time_str(tehran_time)
    signal_source = compose_signal_source(check_result, analysis_data, direction)

    append_signal_row(
        symbol=symbol,
        direction=direction,
        risk_level_name=check_result['risk_name'],
        entry_price=last,
        stop_loss=stop,
        take_profit=target,
        issued_at_tehran=issued_at_tehran,
        signal_source=signal_source,
        position_size_usd=10.0
    )

    logger.info(f"📝 سیگنال در CSV روزانه ذخیره شد: {symbol} {direction} {check_result['risk_name']}")


