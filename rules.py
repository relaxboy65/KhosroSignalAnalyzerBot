from indicators import (
    calculate_ema,
    body_strength,
    rsi_count_ok,
    macd_count_ok,
    no_divergence
)

# =========================================================
# Helper: ساختار روند با تحمل خطا
# =========================================================
def structure_with_tolerance(candles, count, direction, tolerance=0.002):
    if not candles or len(candles) < count:
        return False
    try:
        highs = [c[1] for c in candles[-count:]]
        lows  = [c[2] for c in candles[-count:]]
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
def is_healthy_range(candles, lookback=10, max_range_percent=0.006):
    if not candles or len(candles) < lookback:
        return False
    try:
        highs = [c[1] for c in candles[-lookback:]]
        lows  = [c[2] for c in candles[-lookback:]]
    except Exception:
        return False

    high = max(highs)
    low = min(lows)
    if low <= 0:
        return False

    range_percent = (high - low) / low
    return range_percent <= max_range_percent


# =========================================================
# Helper: MACD خیلی قوی
# =========================================================
def macd_very_strong(macd_vals, direction):
    h30 = macd_vals.get('30m', (None, None))[1]
    h1h = macd_vals.get('1h', (None, None))[1]
    if h30 is None or h1h is None:
        return False

    if direction == 'LONG' and (h30 <= 0 or h1h <= 0):
        return False
    if direction == 'SHORT' and (h30 >= 0 or h1h >= 0):
        return False

    # فشار واقعی: 30m باید قوی‌تر از 1h باشد
    if abs(h30) < abs(h1h) * 0.6:   # کمی نرم‌تر از نسخه قبلی
        return False

    return True
# =========================================================
# Main Rules: ULTRA QUALITY FLEXIBLE + 4h fallback
# =========================================================
def check_rules_ultra_quality_flexible(analysis_data, direction):

    last_close = analysis_data.get('last_close')
    closes = analysis_data.get('closes', {})
    data = analysis_data.get('data', {})

    passed_rules = []
    reasons = []

    # ================= Rule 1: 4h context =================
    if '4h' not in data:
        return fail("داده 4h وجود ندارد")

    trend_4h = structure_with_tolerance(data['4h'], count=5, direction=direction, tolerance=0.002)
    range_4h = is_healthy_range(data['4h'])

    if not (trend_4h or range_4h):
        # انعطاف: اگر 4h نامعتبر است ولی 1h و 30m خیلی قوی هستند → سیگنال ریسک بالا
        strong_1h = '1h' in data and structure_with_tolerance(data['1h'], count=4, direction=direction, tolerance=0.0015)
        if strong_1h and '30m' in data:
            bs30 = body_strength(data['30m'][-1])
            macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, required=3)
            if bs30 >= 0.7 and macd_ok and macd_count >= 4 and macd_very_strong(macd_vals, direction):
                reasons.append("4h نامعتبر ولی 1h و 30m خیلی قوی → عبور با ریسک بالا")
                passed_rules.append("Fallback: قدرت 1h + 30m")
            else:
                return fail("4h نه ترند معتبر است نه رنج سالم")
        else:
            return fail("4h نه ترند معتبر است نه رنج سالم")
    else:
        passed_rules.append("کانتکست 4h معتبر (ترند یا تراکم سالم)")

    # ================= Rule 2: 1h trend =================
    if '1h' not in data or not structure_with_tolerance(data['1h'], count=4, direction=direction, tolerance=0.0015):
        return fail("روند 1h قفل نشده")
    passed_rules.append("روند 1h قفل‌شده")

    # ================= Rule 3: EMA21 30m =================
    if '30m' not in data or len(closes.get('30m', [])) < 30:
        return fail("داده کافی 30m نیست")

    ema21 = calculate_ema(closes['30m'], 21)
    ema21_prev = calculate_ema(closes['30m'][:-5], 21)
    if not ema21_prev:
        return fail("EMA قبلی نامعتبر است")

    ema_slope = (ema21 - ema21_prev) / ema21_prev
    if abs(ema_slope) < 0.0025:
        return fail("EMA21 30m شیب واقعی ندارد")

    if direction == 'LONG' and last_close <= ema21:
        return fail("قیمت زیر EMA21 است")
    if direction == 'SHORT' and last_close >= ema21:
        return fail("قیمت بالای EMA21 است")

    passed_rules.append("EMA21 30m با شیب واقعی")

    # ================= Rule 4: Decision candle =================
    bs30 = body_strength(data['30m'][-1])
    macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, required=3)
    very_strong_macd = macd_very_strong(macd_vals, direction)

    if bs30 < 0.65 and not (macd_ok and macd_count >= 4 and very_strong_macd):
        return fail("کندل تصمیم 30m ضعیف است")
    if bs30 < 0.65:
        reasons.append("کندل متوسط ولی MACD واقعاً قوی")

    passed_rules.append("کندل تصمیم 30m")

    # ================= Rule 5: RSI =================
    rsi_ok, _, rsi_vals = rsi_count_ok(closes, direction, required=4)
    if not rsi_ok:
        return fail("RSI هم‌جهت نیست")

    rsi_30 = rsi_vals.get('30m', 50)
    if direction == 'LONG' and rsi_30 > 68 and not very_strong_macd:
        return fail("RSI نزدیک اشباع است")
    if direction == 'SHORT' and rsi_30 < 32 and not very_strong_macd:
        return fail("RSI نزدیک اشباع است")
    if (direction == 'LONG' and rsi_30 > 68) or (direction == 'SHORT' and rsi_30 < 32):
        reasons.append("RSI نزدیک اشباع ولی MACD قوی")

    passed_rules.append("RSI سالم با فضای حرکت")

    # ================= Rule 6: MACD =================
    if not macd_ok:
        return fail("MACD هم‌جهت نیست")
    passed_rules.append("MACD تثبیت‌شده")

    # ================= Rule 7: No divergence =================
    if not no_divergence(data, closes):
        return fail("واگرایی مشاهده شد")
    passed_rules.append("بدون واگرایی")

    # ================= Final =================
    return {
        'passed': True,
        'passed_rules': passed_rules,
        'passed_count': len(passed_rules),
        'reasons': reasons,
        'risk_name': 'ULTRA QUALITY FLEXIBLE'
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
        'risk_name': 'ULTRA QUALITY FLEXIBLE'
    }


# =========================================================
# Wrapper برای سازگاری با bot.py
# =========================================================
def check_rules_for_level(analysis_data, risk, direction):
    return check_rules_ultra_quality_flexible(analysis_data, direction)
