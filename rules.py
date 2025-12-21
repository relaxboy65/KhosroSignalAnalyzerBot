from indicators import (
    calculate_ema, body_strength,
    hhhl_lhll_structure, rsi_count_ok,
    macd_count_ok, no_divergence
)

def macd_very_strong(macd_vals, direction):
    """
    MACD خیلی قوی = هم‌جهت + فشار واقعی
    """
    h30 = macd_vals.get('30m', (None, None))[1]
    h1h = macd_vals.get('1h', (None, None))[1]

    if h30 is None or h1h is None:
        return False

    # جهت درست
    if direction == 'LONG' and (h30 <= 0 or h1h <= 0):
        return False
    if direction == 'SHORT' and (h30 >= 0 or h1h >= 0):
        return False

    # فشار واقعی: هیستوگرام 30m قوی‌تر از 1h باشد
    if abs(h30) < abs(h1h) * 0.8:
        return False

    return True


def check_rules_ultra_quality_flexible(analysis_data, direction):
    """
    سیستم فوق‌محافظه‌کار + انعطاف کنترل‌شده
    """

    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    data = analysis_data['data']

    passed_rules = []
    reasons = []

    # ================= Rule 1: روند قطعی 4h =================
    if '4h' not in data or not hhhl_lhll_structure(
        data['4h'], count=5, direction=direction
    ):
        return fail("روند 4h تثبیت نشده")

    passed_rules.append("روند 4h قطعی")

    # ================= Rule 2: روند قفل‌شده 1h =================
    if '1h' not in data or not hhhl_lhll_structure(
        data['1h'], count=4, direction=direction
    ):
        return fail("روند 1h قفل نشده")

    passed_rules.append("روند 1h قفل‌شده")

    # ================= Rule 3: EMA21 30m با شیب واقعی =================
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

    # ================= Rule 4: کندل تصمیم 30m =================
    bs30 = body_strength(data['30m'][-1])
    macd_ok, macd_count, macd_vals = macd_count_ok(
        closes, direction, required=3
    )

    very_strong_macd = macd_very_strong(macd_vals, direction)

    if bs30 < 0.65 and not (macd_ok and macd_count >= 4 and very_strong_macd):
        return fail("کندل 30m ضعیف و MACD جبرانی کافی نیست")

    if bs30 < 0.65:
        reasons.append("کندل 30m متوسط ولی MACD واقعاً قوی → عبور")

    passed_rules.append("کندل تصمیم 30m")

    # ================= Rule 5: RSI سالم =================
    rsi_ok, rsi_count, rsi_vals = rsi_count_ok(
        closes, direction, required=4
    )

    if not rsi_ok:
        return fail("RSI هم‌جهت نیست")

    rsi_30 = rsi_vals.get('30m', 50)

    if direction == 'LONG' and rsi_30 > 68 and not very_strong_macd:
        return fail("RSI نزدیک اشباع است")

    if direction == 'SHORT' and rsi_30 < 32 and not very_strong_macd:
        return fail("RSI نزدیک اشباع است")

    if (direction == 'LONG' and rsi_30 > 68) or (direction == 'SHORT' and rsi_30 < 32):
        reasons.append("RSI نزدیک اشباع ولی MACD واقعاً قوی → عبور")

    passed_rules.append("RSI سالم با فضای حرکت")

    # ================= Rule 6: MACD تثبیت‌شده =================
    if not macd_ok:
        return fail("MACD هم‌جهت نیست")

    passed_rules.append("MACD تثبیت‌شده")

    # ================= Rule 7: عدم واگرایی =================
    if not no_divergence(data, closes):
        return fail("واگرایی مشاهده شد")

    passed_rules.append("بدون واگرایی")

    # ================= تصمیم نهایی =================
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


# ========== Wrapper برای سازگاری با bot.py ==========
def check_rules_for_level(analysis_data, risk, direction):
    """
    Wrapper برای فراخوانی نسخه ULTRA QUALITY FLEXIBLE
    bot.py سه آرگومان می‌دهد (analysis, risk, direction)
    ولی تابع اصلی فقط دو آرگومان می‌گیرد.
    """
    return check_rules_ultra_quality_flexible(analysis_data, direction)

