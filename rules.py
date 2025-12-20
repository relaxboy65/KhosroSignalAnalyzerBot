# rules.py
# نسخه نهایی و بهینه‌شده قوانین سیگنال‌دهی
# تغییرات کلیدی:
# - EMA در 4h و 1h برای MEDIUM/HIGH حذف شد، فقط ساختار کندلی باقی مانده
# - EMA21 در 30m با فیلتر شیب برای جلوگیری از ورود در بازار رنج
# - Rule 5: ورود + حجم فقط با ری‌تست معتبر
# - Rule 6: RSI با شدت + جلوگیری از اشباع کوتاه‌مدت
# - Rule 7: MACD با شدت هیستوگرام + دروازه چند‌تایم‌فریم
# - آستانه HIGH از 5 به 4 کاهش یافت
# - متن خروجی استانداردسازی شده برای جلوگیری از خطای تلگرام

from indicators import (
    calculate_ema, calculate_rsi, calculate_macd, body_strength,
    is_near, hhhl_lhll_structure, swing_levels, broke_level,
    rsi_count_ok, macd_count_ok, no_divergence
)

def check_rules_for_level(analysis_data, risk_config, direction):
    """
    بررسی قوانین برای یک سطح ریسک و یک جهت (LONG یا SHORT)
    بازگشت دیکشنری شامل تصمیم، تعداد قوانین پاس‌شده، نام قوانین و دلایل
    """
    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    data = analysis_data['data']

    passed_rules = []
    reasons = []

    risk_key = risk_config['key']

    # ========== Rule 1: روند 4h ==========
    if '4h' in data:
        candles_4h = data['4h']
        struct_count = 5 if risk_key == 'LOW' else 4 if risk_key == 'MEDIUM' else 3
        struct_ok = hhhl_lhll_structure(candles_4h, count=struct_count, direction=direction)
        if struct_ok:
            passed_rules.append('روند 4h')
            reasons.append(f"ساختار {'HH/HL' if direction == 'LONG' else 'LH/LL'} در {struct_count} کندل 4h")

    # ========== Rule 2: روند 1h ==========
    if '1h' in data:
        candles_1h = data['1h']
        struct_count_1h = 4 if risk_key == 'LOW' else 4 if risk_key == 'MEDIUM' else 3
        struct_ok = hhhl_lhll_structure(candles_1h, count=struct_count_1h, direction=direction)
        if struct_ok:
            passed_rules.append('روند 1h')
            reasons.append(f"ساختار {'HH/HL' if direction == 'LONG' else 'LH/LL'} در {struct_count_1h} کندل 1h")

    # ========== Rule 3: EMA21 + ساختار در 30m ==========
    if '30m' in data and len(closes.get('30m', [])) >= 24:
        ema21_30m = calculate_ema(closes['30m'], 21)
        ema21_prev_30m = calculate_ema(closes['30m'][:-3], 21) if len(closes['30m']) >= 24 else None
        ema_slope_30m = None
        if ema21_prev_30m and ema21_prev_30m != 0:
            ema_slope_30m = (ema21_30m - ema21_prev_30m) / ema21_prev_30m
        slope_thr = 0.0015 if risk_key == 'LOW' else 0.0010 if risk_key == 'MEDIUM' else 0.0008
        slope_ok = (ema_slope_30m is None) or (abs(ema_slope_30m) >= slope_thr)
        price_ok = (direction == 'LONG' and last_close > ema21_30m) or (direction == 'SHORT' and last_close < ema21_30m)
        if risk_key == 'HIGH':
            if price_ok and slope_ok:
                passed_rules.append('EMA21 30m')
                reasons.append("قیمت همسو با EMA21 در 30m + شیب مناسب")
        else:
            struct_ok_30m = hhhl_lhll_structure(data['30m'], count=3, direction=direction)
            if price_ok and struct_ok_30m and slope_ok:
                passed_rules.append('EMA21 + ساختار 30m')
                reasons.append("قیمت همسو با EMA21 + ساختار در 30m + شیب مناسب")

    # ========== Rule 4: قدرت کندل 15m ==========
    if '15m' in data and len(data['15m']) >= 1:
        bs15 = body_strength(data['15m'][-1])
        if risk_key == 'LOW':
            thr = 0.60
        elif risk_key == 'MEDIUM':
            thr = 0.45
        else:  # HIGH
            thr = 0.40
        if bs15 > thr:
            passed_rules.append('کندل قوی 15m')
            reasons.append(f"قدرت کندل 15m = {bs15:.2f} [حد > {thr}]")

    # ========== Rule 5: ورود + حجم ==========
    if '5m' in data and len(data['5m']) >= 12:
        sh, sl = swing_levels(data['5m'], lookback=10)
        level = sh if direction == 'LONG' else sl
        near_ok = is_near(last_close, level, 0.003)
        vol_5m = data['5m'][-1]['v']
        avg_vol_5m = sum(c['v'] for c in data['5m'][-10:]) / 10.0 if data['5m'] else 0
        vol_threshold = 1.3 if risk_key == 'LOW' else 1.2 if risk_key == 'MEDIUM' else 1.1
        vol_ok = avg_vol_5m > 0 and vol_5m >= vol_threshold * avg_vol_5m
        last3 = data['5m'][-3:]
        max_spike_vol = max(c['v'] for c in last3)
        bs5 = body_strength(data['5m'][-1])
        retest_ok = near_ok and (vol_5m <= 0.9 * max_spike_vol) and (0.30 <= bs5 <= 0.85)
        if retest_ok and vol_ok:
            passed_rules.append('ورود + حجم')
            reasons.append(f"ری‌تست سطح + حجم ≥{vol_threshold}x + BS5={bs5:.2f}")
    # ========== Rule 6: RSI (با شدت + جلوگیری از اشباع کوتاه‌مدت بدون ری‌تست) ==========
    req_rsi = risk_config['rules'].get('rsi_threshold_count', 3)
    rsi_ok, rsi_count, rsi_vals = rsi_count_ok(closes, direction, req_rsi)
    extra_rsi = sum(1 for v in rsi_vals.values() if (direction == 'LONG' and v > 70) or (direction == 'SHORT' and v < 30))

    rsi_exhaust_long = (direction == 'LONG' and rsi_vals.get('15m', 50) > 75 and rsi_vals.get('30m', 50) > 70)
    rsi_exhaust_short = (direction == 'SHORT' and rsi_vals.get('15m', 50) < 25 and rsi_vals.get('30m', 50) < 30)

    if risk_key == 'LOW':
        rsi_condition = rsi_count >= 4 and extra_rsi >= 2 and not (rsi_exhaust_long or rsi_exhaust_short)
    elif risk_key == 'MEDIUM':
        rsi_condition = rsi_count >= 3 and extra_rsi >= 1 and not (rsi_exhaust_long or rsi_exhaust_short)
    else:  # HIGH
        rsi_condition = (rsi_count >= 2 or extra_rsi >= 1) and not (rsi_exhaust_long or rsi_exhaust_short)

    if rsi_condition:
        passed_rules.append('RSI')
        reasons.append(f"RSI: {rsi_count}/5 همسو + {extra_rsi} خیلی قوی [آستانه 70/30]")

    # ========== Rule 7: MACD (با شدت هیستوگرام + دروازه چند‌تایم‌فریم) ==========
    req_macd = risk_config['rules'].get('macd_threshold_count', 3)
    macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, req_macd)
    extra_macd = 0
    hist_values = [v[1] for v in macd_vals.values() if v[1] is not None]

    if len(hist_values) >= 5:
        avg_hist = sum(abs(h) for h in hist_values[-5:]) / 5.0
        multiplier = 1.3 if risk_key == 'LOW' else 1.2 if risk_key == 'MEDIUM' else 1.1
        for h in hist_values[-3:]:
            if (direction == 'LONG' and h > avg_hist * multiplier) or (direction == 'SHORT' and h < -avg_hist * multiplier):
                extra_macd += 1

    # دروازه هم‌جهتی هیستوگرام MACD در تایم‌فریم‌های مختلف
    h30 = macd_vals.get('30m', (None, None))[1]
    h1h = macd_vals.get('1h', (None, None))[1]
    h4h = macd_vals.get('4h', (None, None))[1]

    macd_hist_gate = True
    if direction == 'LONG':
        if (h30 is not None and h30 < 0) or (h1h is not None and h1h < 0):
            macd_hist_gate = False
        if (h4h is not None and h4h < 0):
            macd_hist_gate = (extra_macd >= 2 and macd_count >= 3)
    else:  # SHORT
        if (h30 is not None and h30 > 0) or (h1h is not None and h1h > 0):
            macd_hist_gate = False
        if (h4h is not None and h4h > 0):
            macd_hist_gate = (extra_macd >= 2 and macd_count >= 3)

    macd_condition = (macd_ok or extra_macd >= 1) and macd_hist_gate
    if macd_condition:
        passed_rules.append('MACD')
        reasons.append(f"MACD: {macd_count}/5 همسو + {extra_macd} شدت قوی + گیت هیستوگرام")

    # ========== Rule 8: عدم واگرایی ==========
    if no_divergence(data, closes):
        passed_rules.append('عدم واگرایی')
        reasons.append("بدون واگرایی در 1h و 4h")

    # ========== Rule 9: حجم اسپایک + قدرت کندل در 15m ==========
    if '15m' in data and len(data['15m']) >= 10:
        vol_15m = data['15m'][-1]['v']
        avg_vol_15m = sum(c['v'] for c in data['15m'][-10:]) / 10.0
        vol_multiplier = 1.3 if risk_key == 'LOW' else 1.2 if risk_key == 'MEDIUM' else 1.1
        bs15 = body_strength(data['15m'][-1])
        bs_thr = 0.6 if risk_key == 'LOW' else 0.45 if risk_key == 'MEDIUM' else 0.40
        if avg_vol_15m > 0 and vol_15m >= vol_multiplier * avg_vol_15m and bs15 > bs_thr:
            passed_rules.append('حجم + کندل 15m')
            reasons.append(f"حجم اسپایک [≥{vol_multiplier}x] + قدرت کندل 15m = {bs15:.2f}")

    # ========== تصمیم نهایی ==========
    passed_count = len(passed_rules)

    if risk_key == 'LOW':
        decision = passed_count >= 7
    elif risk_key == 'MEDIUM':
        decision = passed_count >= 6
    else:  # HIGH
        decision = passed_count >= 4  # آستانه HIGH از 5 به 4 کاهش یافت

    return {
        'passed': decision,
        'passed_count': passed_count,
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': risk_config['name'],
    }
