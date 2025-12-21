from indicators import (
    calculate_ema, body_strength,
    rsi_count_ok, macd_count_ok, no_divergence
)

# ================= Helper: Structure with tolerance =================
def structure_with_tolerance(candles, count, direction, tolerance=0.002):
    """
    تشخیص HH/HL یا LH/LL با تحمل نوسان
    سازگار با candles به‌صورت tuple/list
    فرض ساختار: (open, high, low, close, ...)
    """

    if len(candles) < count:
        return False

    try:
        highs = [c[1] for c in candles[-count:]]  # high
        lows  = [c[2] for c in candles[-count:]]  # low
    except Exception:
        return False  # دیتای خراب یا ساختار غیرمنتظره

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

# ================= Helper: MACD very strong =================
def macd_very_strong(macd_vals, direction):
    h30 = macd_vals.get('30m', (None, None))[1]
    h1h = macd_vals.get('1h', (None, None))[1]

    if h30 is None or h1h is None:
        return False

    if direction == 'LONG' and (h30 <= 0 or h1h <= 0):
        return False
    if direction == 'SHORT' and (h30 >= 0 or h1h >= 0):
        return False

    # فشار واقعی، نه خاطره‌ی حرکت
    if abs(h30) < abs(h1h) * 0.8:
        return False

    return True


# ================= Main Rules =================
def check_rules_ultra_quality_flexible(analysis_data, direction):

    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    data = analysis_data['data']

    passed_rules = []
    reasons = []

    # ========= Rule 1: 4h trend (tolerant) =========
    if '4h' not in data or not structure_with_tolerance(
        data['4h'], count=5, direction=direction, tolerance=0.002
    ):
        return fail("روند 4h معتبر نیست")

    passed_rules.append("روند 4h معتبر")

    # ========= Rule 2: 1h trend (tighter) =========
    if '1h' not in data or not structure_with_tolerance(
        data['1h'], count=4, direction=direction, tolerance=0.0015
    ):
        return fail("روند 1h قفل نشده")

    passed_rules.append("روند 1h قفل‌شده")

    # ========= Rule 3: EMA21 30m =========
    if '30m' not in data or len(closes.get('30m', [])) < 30:
        return fail("داده کافی 30m نیست")

    ema21 = calculate_ema(closes['30m'], 21)
    ema21_prev = calculate_ema(closes['30m'][:-5], 21)
    ema_slope = (ema21 - ema21_prev) / ema21_prev if ema21_prev else 0

    if abs(ema_slope) < 0.0025:
        return fail("EMA21 30m شیب واقعی ندارد")

    if direction == 'LONG' and last_close <= ema21:
        return fail("قیمت زیر EMA21 است")
    if direction == 'SHORT' and last_close >= ema21:
        return fail("قیمت بالای EMA21 است")

    passed_rules.append("EMA21 30m با شیب واقعی")

    # ========= Rule 4: Decision candle =========
    bs30 = body_strength(data['30m'][-1])
    macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, required=3)
    very_strong = macd_very_strong(macd_vals, direction)

    if bs30 < 0.65 and not (macd_ok and macd_count >= 4 and very_strong):
        return fail("کندل 30m ضعیف")

    if bs30 < 0.65:
        reasons.append("کندل متوسط ولی MACD واقعاً قوی")

    passed_rules.append("کندل تصمیم 30m")

    # ========= Rule 5: RSI =========
    rsi_ok, _, rsi_vals = rsi_count_ok(closes, direction, required=4)
    if not rsi_ok:
        return fail("RSI هم‌جهت نیست")

    rsi_30 = rsi_vals.get('30m', 50)

    if direction == 'LONG' and rsi_30 > 68 and not very_strong:
        return fail("RSI نزدیک اشباع")
    if direction == 'SHORT' and rsi_30 < 32 and not very_strong:
        return fail("RSI نزدیک اشباع")

    if (direction == 'LONG' and rsi_30 > 68) or (direction == 'SHORT' and rsi_30 < 32):
        reasons.append("RSI نزدیک اشباع ولی MACD قوی")

    passed_rules.append("RSI سالم")

    # ========= Rule 6: MACD =========
    if not macd_ok:
        return fail("MACD هم‌جهت نیست")

    passed_rules.append("MACD تثبیت‌شده")

    # ========= Rule 7: No divergence =========
    if not no_divergence(data, closes):
        return fail("واگرایی دیده شد")

    passed_rules.append("بدون واگرایی")

    return {
        'passed': True,
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': 'ULTRA QUALITY FLEXIBLE'
    }


def fail(reason):
    return {
        'passed': False,
        'passed_rules': [],
        'passed_count': 0,
        'reasons': [reason],
        'risk_name': 'ULTRA QUALITY FLEXIBLE'
    }


def check_rules_for_level(analysis_data, risk, direction):
    return check_rules_ultra_quality_flexible(analysis_data, direction)
