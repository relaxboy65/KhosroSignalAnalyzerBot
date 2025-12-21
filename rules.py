from indicators import (
    calculate_ema,
    body_strength,
    rsi_count_ok,
    macd_count_ok,
    no_divergence
)
import numpy as np

# =========================================================
# Helper: ساختار روند با تحمل خطا
# =========================================================
def structure_with_tolerance(candles, count, direction, tolerance=0.002):
    if not candles or len(candles) < count:
        return False
    try:
        highs, lows = [], []
        for c in candles[-count:]:
            o, h, l, cl = get_prices(c)
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
            o, h, l, cl = get_prices(c)
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

    o_cur, h_cur, l_cur, c_cur = get_prices(current_candle)
    o_prev, h_prev, l_prev, c_prev = get_prices(prev_candle)

    if o_cur is None or c_cur is None or o_prev is None or c_prev is None:
        return False, "ساختار کندل نامعتبر"

    bs_current = body_strength(current_candle)
    bs_prev = body_strength(prev_candle)

    # کندل فعلی باید قوی باشد
    if bs_current < 0.4:
        return False, f"کندل فعلی ضعیف: {bs_current:.2f}"

    # کندل قبلی نباید مخالف قوی باشد
    if direction == 'LONG' and c_prev < o_prev:  # کندل نزولی
        if bs_prev > 0.4:
            return False, "کندل قبلی نزولی قوی"
    elif direction == 'SHORT' and c_prev > o_prev:  # کندل صعودی
        if bs_prev > 0.4:
            return False, "کندل قبلی صعودی قوی"

    return True, "قدرت ورود مناسب"

# =========================================================
# Helper: استخراج قیمت‌ها از کندل (سازگار با dict و list)
# =========================================================
def get_prices(candle):
    if isinstance(candle, dict):
        return candle.get('open'), candle.get('high'), candle.get('low'), candle.get('close')
    elif isinstance(candle, (list, tuple)) and len(candle) >= 4:
        return candle[0], candle[1], candle[2], candle[3]
    else:
        return None, None, None, None

    open_cur, high_cur, low_cur, close_cur = get_prices(current_candle)
    open_prev, high_prev, low_prev, close_prev = get_prices(prev_candle)

    if open_cur is None or close_cur is None:
        return False, "ساختار کندل نامعتبر"

    bs_current = body_strength(current_candle)
    bs_prev = body_strength(prev_candle)

    # کندل فعلی باید قوی باشد
    if bs_current < 0.4:
        return False, f"کندل فعلی ضعیف: {bs_current:.2f}"

    # کندل قبلی نباید مخالف قوی باشد
    if direction == 'LONG' and close_prev < open_prev:
        if bs_prev > 0.4:
            return False, "کندل قبلی نزولی قوی"
    elif direction == 'SHORT' and close_prev > open_prev:
        if bs_prev > 0.4:
            return False, "کندل قبلی صعودی قوی"

    return True, "قدرت ورود مناسب"



# =========================================================
# Helper: بررسی فاصله داینامیک EMA21
# =========================================================
def check_ema_distance_dynamic(last_close, ema21, atr_percent):
    """
    فاصله داینامیک EMA21 بر اساس نوسان بازار
    """
    if atr_percent < 0.005:  # نوسان کم (مثل BTC آرام)
        min_distance = 0.001  # 0.1%
    elif atr_percent < 0.015:  # نوسان متوسط
        min_distance = 0.002  # 0.2%
    else:  # نوسان بالا (altcoin ها)
        min_distance = 0.003  # 0.3%
    
    price_vs_ema = abs(last_close - ema21) / ema21
    return price_vs_ema >= min_distance, price_vs_ema, min_distance


# =========================================================
# Helper: بررسی شیب EMA21
# =========================================================
def check_ema_slope(closes_30m, period=21, lookback_candles=5):
    """
    بررسی شیب EMA21 در کندل‌های اخیر
    حداقل شیب مورد نیاز: 0.1% در 5 کندل گذشته
    """
    if len(closes_30m) < period + lookback_candles:
        return None, "داده ناکافی برای محاسبه شیب EMA"
    
    # محاسبه EMA برای کندل فعلی و lookback_candles کندل قبل
    ema_current = calculate_ema(closes_30m, period)
    
    # محاسبه EMA برای کندل‌های گذشته
    closes_past = closes_30m[:-lookback_candles]
    if len(closes_past) >= period:
        ema_past = calculate_ema(closes_past, period)
    else:
        return None, "داده گذشته ناکافی"
    
    if ema_past == 0:
        return None, "EMA گذشته صفر"
    
    slope = (ema_current - ema_past) / ema_past
    slope_percent = slope * 100
    
    # حداقل شیب مورد نیاز: 0.1%
    min_slope_percent = 0.1 if lookback_candles == 5 else 0.2
    
    return {
        'slope': slope,
        'slope_percent': slope_percent,
        'min_required': min_slope_percent,
        'passed': abs(slope_percent) >= min_slope_percent,
        'direction': 'up' if slope > 0 else 'down' if slope < 0 else 'flat'
    }, None


# =========================================================
# Helper: بررسی قدرت داینامیک MACD (خلاصه‌شده)
# =========================================================
def check_macd_strength_dynamic(macd_vals, direction, risk_level, symbol_volatility):
    """
    بررسی قدرت MACD بر اساس نوسان نماد
    خروجی خلاصه: فقط اطلاعات ضروری
    """
    strong_count = 0
    very_strong_count = 0
    total_strength = 0
    strongest_tf = None
    strongest_value = 0
    
    # تنظیم threshold بر اساس نوسان نماد
    if symbol_volatility < 0.01:  # کم نوسان (مثل BTC آرام)
        strength_threshold = 0.3
    elif symbol_volatility < 0.03:  # نوسان متوسط
        strength_threshold = 0.5
    else:  # پرنوسان (altcoin ها)
        strength_threshold = 0.8
    
    # وزن تایم‌فریم‌ها (تایم‌فریم‌های میانی اهمیت بیشتری دارند)
    tf_weights = {'5m': 0.5, '15m': 1.0, '30m': 1.5, '1h': 2.0, '4h': 1.0}
    
    for tf, (macd_line, hist) in macd_vals.items():
        weight = tf_weights.get(tf, 1.0)
        
        if direction == 'LONG' and hist > 0:
            strong_count += 1
            hist_strength = abs(hist) * weight
            total_strength += hist_strength
            
            if hist_strength > strength_threshold:
                very_strong_count += 1
            
            # پیدا کردن قوی‌ترین تایم‌فریم
            if hist_strength > strongest_value:
                strongest_value = hist_strength
                strongest_tf = tf
                
        elif direction == 'SHORT' and hist < 0:
            strong_count += 1
            hist_strength = abs(hist) * weight
            total_strength += hist_strength
            
            if hist_strength > strength_threshold:
                very_strong_count += 1
            
            if hist_strength > strongest_value:
                strongest_value = hist_strength
                strongest_tf = tf
    
    # تنظیمات بر اساس سطح ریسک
    if risk_level == "ریسک میانی":
        min_strong = 3
        min_total_strength = 2.0
        min_very_strong = 1
    else:  # ریسک بالا
        min_strong = 2
        min_total_strength = 1.0
        min_very_strong = 0
    
    passed = (
        strong_count >= min_strong and
        total_strength >= min_total_strength and
        very_strong_count >= min_very_strong
    )
    
    # خروجی خلاصه شده
    summary = {
        'strong_count': strong_count,
        'very_strong_count': very_strong_count,
        'total_strength': round(total_strength, 2),
        'strongest': f"{strongest_tf}({strongest_value:.2f})" if strongest_tf else "ندارد",
        'passed': passed
    }
    
    return passed, summary


# =========================================================
# Helper: بررسی RSI اشباع شدید
# =========================================================
def check_rsi_extreme(rsi_vals, direction, risk_level):
    """
    بررسی اشباع شدید RSI در تایم‌فریم‌های مختلف
    حتی در ریسک بالا، RSI خیلی شدید باید رد شود
    """
    # آستانه‌های اشباع بحرانی (رد قطعی)
    extreme_critical = {
        '5m': {'LONG': 85, 'SHORT': 15},
        '15m': {'LONG': 82, 'SHORT': 18},
        '30m': {'LONG': 80, 'SHORT': 20},
        '1h': {'LONG': 78, 'SHORT': 22},
        '4h': {'LONG': 75, 'SHORT': 25}
    }
    
    # آستانه‌های هشدار (برای ریسک میانی رد، برای ریسک بالا هشدار)
    extreme_warning = {
        '5m': {'LONG': 80, 'SHORT': 20},
        '15m': {'LONG': 78, 'SHORT': 22},
        '30m': {'LONG': 75, 'SHORT': 25},
        '1h': {'LONG': 72, 'SHORT': 28},
        '4h': {'LONG': 70, 'SHORT': 30}
    }
    
    for tf, rsi_value in rsi_vals.items():
        if tf not in extreme_critical:
            continue
            
        if direction == 'LONG':
            # بررسی اشباع بحرانی (رد در همه سطوح ریسک)
            if rsi_value >= extreme_critical[tf]['LONG']:
                return False, f"RSI {tf} در اشباع خرید بحرانی: {rsi_value:.1f}"
            
            # بررسی هشدار
            if rsi_value >= extreme_warning[tf]['LONG']:
                if risk_level == "ریسک میانی":
                    return False, f"RSI {tf} در اشباع خرید: {rsi_value:.1f}"
                    
        elif direction == 'SHORT':
            # بررسی اشباع بحرانی
            if rsi_value <= extreme_critical[tf]['SHORT']:
                return False, f"RSI {tf} در اشباع فروش بحرانی: {rsi_value:.1f}"
            
            # بررسی هشدار
            if rsi_value <= extreme_warning[tf]['SHORT']:
                if risk_level == "ریسک میانی":
                    return False, f"RSI {tf} در اشباع فروش: {rsi_value:.1f}"
    
    return True, "RSI در محدوده قابل قبول"


# =========================================================
# Helper: بررسی فاصله داینامیک از حمایت/مقاومت
# =========================================================
def check_support_resistance_dynamic(data_4h, current_price, direction, symbol=""):
    """بررسی فاصله از سطوح کلیدی به صورت داینامیک"""
    if not data_4h or len(data_4h) < 20:
        return True, "داده ناکافی برای تحلیل سطوح"
    
    # محاسبه نوسان نماد
    recent_candles = data_4h[-20:]
    highs = [c[1] for c in recent_candles]
    lows = [c[2] for c in recent_candles]
    
    price_range = max(highs) - min(lows)
    avg_price = (max(highs) + min(lows)) / 2
    volatility = price_range / avg_price if avg_price > 0 else 0.02
    
    # تنظیم حداقل فاصله بر اساس نوسان
    if volatility < 0.02:  # کم نوسان
        min_distance = 0.008  # 0.8%
    elif volatility < 0.05:  # نوسان متوسط
        min_distance = 0.012  # 1.2%
    else:  # پرنوسان
        min_distance = 0.02  # 2.0%
    
    # تنظیمات سفارشی برای نمادهای خاص
    symbol_settings = {
        'BTC-USDT': 0.006,   # BTC نیاز به فاصله کمتری دارد
        'ETH-USDT': 0.007,
        'XAUT-USDT': 0.005,  # طلای دیجیتال پایدار
        'SOL-USDT': 0.015,   # SOL نوسان بیشتری دارد
        'ATOM-USDT': 0.01,
        'FIL-USDT': 0.018,
        'XLM-USDT': 0.01,
        'TRX-USDT': 0.008,
        'ADA-USDT': 0.01,
        'DOGE-USDT': 0.015,
    }
    
    if symbol in symbol_settings:
        min_distance = symbol_settings[symbol]
    
    # یافتن نزدیک‌ترین سطوح
    nearest_resistance = min([h for h in highs if h > current_price], default=None)
    nearest_support = max([l for l in lows if l < current_price], default=None)
    
    if direction == 'LONG' and nearest_resistance:
        distance = (nearest_resistance - current_price) / current_price
        if distance < min_distance:
            return False, f"نزدیک مقاومت: {distance:.2%}"
    
    if direction == 'SHORT' and nearest_support:
        distance = (current_price - nearest_support) / current_price
        if distance < min_distance:
            return False, f"نزدیک حمایت: {distance:.2%}"
    
    return True, f"فاصله مناسب"


# =========================================================
# Helper: محاسبه نوسان نماد (ATR تقریبی)
# =========================================================
def calculate_symbol_volatility(data_30m):
    """محاسبه نوسان نسبی نماد بر اساس داده‌های 30 دقیقه"""
    if not data_30m or len(data_30m) < 20:
        return 0.02  # پیش‌فرض 2%
    
    try:
        recent_data = data_30m[-20:]
        highs = [c[1] for c in recent_data]
        lows = [c[2] for c in recent_data]
        
        high_max = max(highs)
        low_min = min(lows)
        avg_price = (sum(highs) + sum(lows)) / (len(highs) + len(lows))
        
        if avg_price > 0:
            volatility = (high_max - low_min) / avg_price
            return max(0.005, min(volatility, 0.1))
        return 0.02
    except:
        return 0.02


# =========================================================
# Helper: بررسی حجم معاملات داینامیک
# =========================================================
def check_volume_dynamic(current_volume, avg_volume, symbol_volatility, timeframe='15m'):
    """
    بررسی حجم معاملات به صورت داینامیک
    بر اساس نوسان نماد و تایم‌فریم
    """
    if avg_volume <= 0:
        return True, "حجم میانگین نامعتبر", 1.0
    
    volume_ratio = current_volume / avg_volume
    
    # تنظیم حداقل volume spike بر اساس نوسان
    if symbol_volatility < 0.01:  # کم نوسان
        min_ratio = 1.4  # 40% افزایش
    elif symbol_volatility < 0.03:  # نوسان متوسط
        min_ratio = 1.6  # 60% افزایش
    else:  # پرنوسان
        min_ratio = 1.8  # 80% افزایش
    
    # تنظیم بر اساس تایم‌فریم
    if timeframe == '5m':
        min_ratio *= 1.2  # در تایم‌فریم کوتاه نیاز به spike بزرگتر
    elif timeframe == '1h':
        min_ratio *= 0.9  # در تایم‌فریم بلند spike کوچکتر قابل قبول است
    
    if volume_ratio >= min_ratio:
        return True, f"حجم مناسب ({volume_ratio:.1f}x)", volume_ratio
    else:
        return False, f"حجم ناکافی ({volume_ratio:.1f}x < {min_ratio:.1f}x)", volume_ratio


# =========================================================
# MAIN RULES: ULTIMATE TP MAXIMIZER v5 (اصلاح نهایی)
# =========================================================
def check_rules_ultimate_tp_maximizer(analysis_data, direction):
    """
    قوانین نهایی برای حداکثر TP و حداقل استاپ
    نسخه 5: با اصلاحات نهایی
    """
    
    last_close = analysis_data.get('last_close')
    closes = analysis_data.get('closes', {})
    data = analysis_data.get('data', {})
    
    passed_rules = []
    reasons = []
    risk_name = "ریسک میانی"
    symbol = analysis_data.get('symbol', '')
    
    # --- پیش‌فیلتر: داده‌های کافی ---
    if '15m' not in data or len(data['15m']) < 3:
        return fail("داده 15m ناکافی")
    if '30m' not in data or len(data['30m']) < 3:
        return fail("داده 30m ناکافی")
    if '1h' not in data or len(data['1h']) < 5:
        return fail("داده 1h ناکافی")
    
    # محاسبه نوسان نماد
    symbol_volatility = calculate_symbol_volatility(data.get('30m', []))
    
    # --- Rule 1: قدرت واقعی ورود ---
    entry_power_ok, entry_msg = has_real_entry_power(data['15m'], direction)
    if not entry_power_ok:
        return fail(entry_msg)
    passed_rules.append("قدرت ورود")
    
# --- Rule 2: روند 1h ---
if '1h' not in data or not structure_with_tolerance(data['1h'], 3, direction, tolerance=0.002):
    # جایگزین: دو کندل قوی هم‌جهت
    if len(data['1h']) >= 2:
        last_candle = data['1h'][-1]
        prev_candle = data['1h'][-2]

        o_last, h_last, l_last, c_last = get_prices(last_candle)
        o_prev, h_prev, l_prev, c_prev = get_prices(prev_candle)

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
        # فال‌بک ریسک بالا
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
    
    # --- Rule 4: کندل تصمیم (BS15) - با اصلاح شما ---
    bs15 = body_strength(data['15m'][-1])
    
    # اصلاح نهایی با پیشنهاد شما:
    # ریسک میانی: 0.55 | ریسک بالا: 0.50
    if risk_name == "ریسک میانی":
        if bs15 < 0.55:  # از 0.52 به 0.55
            return fail(f"کندل 15m ضعیف: {bs15:.2f}")
    else:  # ریسک بالا
        if bs15 < 0.50:  # از 0.48 به 0.50
            return fail(f"کندل 15m ضعیف: {bs15:.2f}")
    
    passed_rules.append(f"کندل قوی ({bs15:.2f})")
    
    # --- Rule 5: RSI (با بررسی اشباع شدید) ---
    rsi_ok, rsi_count, rsi_vals = rsi_count_ok(closes, direction, required=3)
    if not rsi_ok:
        return fail(f"RSI هم‌جهت کافی نیست: {rsi_count}/5")
    
    # بررسی اشباع شدید RSI
    rsi_extreme_ok, rsi_extreme_msg = check_rsi_extreme(rsi_vals, direction, risk_name)
    if not rsi_extreme_ok:
        return fail(rsi_extreme_msg)
    
    passed_rules.append(f"RSI ({rsi_count}/5)")
    
    # --- Rule 6: MACD (با قدرت داینامیک و خروجی خلاصه) ---
    macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, required=3)
    if not macd_ok:
        return fail(f"MACD هم‌جهت کافی نیست: {macd_count}/5")
    
    # بررسی قدرت MACD به صورت داینامیک
    macd_strength_ok, macd_summary = check_macd_strength_dynamic(
        macd_vals, direction, risk_name, symbol_volatility
    )
    if not macd_strength_ok:
        return fail(f"MACD قدرت کافی ندارد")
    
    # فقط خلاصه مهم در reasons
    reasons.append(f"MACD: {macd_summary['strong_count']}/5 همسو | قدرت: {macd_summary['total_strength']}")
    passed_rules.append("MACD قوی")
    
    # --- Rule 7: عدم واگرایی ---
    if not no_divergence(data, closes):
        return fail("واگرایی مشاهده شد")
    passed_rules.append("بدون واگرایی")
    
    # --- Rule 8: فاصله از سطوح کلیدی ---
    if '4h' in data:
        sr_ok, sr_msg = check_support_resistance_dynamic(
            data['4h'], last_close, direction, symbol
        )
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
            # محاسبه ATR تقریبی
            recent_prices = closes['30m'][-14:]
            if len(recent_prices) >= 10:
                price_range = max(recent_prices) - min(recent_prices)
                avg_price = np.mean(recent_prices)
                atr_simple = price_range / avg_price if avg_price > 0 else 0.01
                
                # بررسی فاصله
                ema_ok, ema_distance, min_req = check_ema_distance_dynamic(
                    last_close, ema21, atr_simple
                )
                
                if not ema_ok:
                    reasons.append(f"فاصله EMA: {ema_distance:.3%}")
                
                # بررسی شیب EMA21
                ema_slope_info, slope_error = check_ema_slope(closes['30m'], period=21, lookback_candles=5)
                if ema_slope_info and ema_slope_info['passed']:
                    passed_rules.append(f"شیب EMA ({ema_slope_info['direction']})")
    
    # --- Rule 10: حجم معاملات داینامیک ---
    if 'volume' in analysis_data and len(analysis_data['volume']) >= 10:
        recent_vol = analysis_data['volume'][-10:]
        avg_vol = sum(recent_vol[-5:]) / 5
        current_vol = recent_vol[-1] if recent_vol else 0
        
        volume_ok, volume_msg, volume_ratio = check_volume_dynamic(
            current_vol, avg_vol, symbol_volatility, '15m'
        )
        
        if volume_ok:
            passed_rules.append("حجم مناسب")
            reasons.append(f"حجم: {volume_ratio:.1f}x")
        else:
            reasons.append(volume_msg)  # فقط هشدار، رد نمی‌کنیم
    
    # جمع‌بندی
    return {
        'passed': True,
        'passed_rules': passed_rules,
        'passed_count': len(passed_rules),
        'reasons': reasons,
        'risk_name': risk_name,
        'bs15': bs15,
        'rsi_count': rsi_count,
        'macd_summary': macd_summary  # فقط خلاصه
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
