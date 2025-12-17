# rules.py
from indicators import (
    calculate_ema, calculate_rsi, calculate_macd, body_strength,
    is_near, hhhl_lhll_structure, swing_levels, broke_level,
    rsi_count_ok, macd_count_ok, no_divergence
)

def check_rules_for_level(analysis_data, risk_config, direction):
    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    data = analysis_data['data']

    passed_rules = []
    reasons = []

    risk_key = risk_config['key']

    # ========== Rule 1: روند 4h (EMA + ساختار؛ برای HIGH ساده‌تر) ==========
    if '4h' in data and '4h' in closes and len(closes['4h']) >= 55:
        candles_4h = data['4h']
        ema21 = calculate_ema(closes['4h'], 21)
        ema55 = calculate_ema(closes['4h'], 55)
        ema200 = calculate_ema(closes['4h'], 200) if len(closes['4h']) >= 200 else None

        ema_details = []
        if ema21 is not None and ((direction == 'LONG' and last_close > ema21) or (direction == 'SHORT' and last_close < ema21)):
            ema_details.append("EMA21")
        if ema55 is not None and ((direction == 'LONG' and last_close > ema55) or (direction == 'SHORT' and last_close < ema55)):
            ema_details.append("EMA55")
        if ema200 is not None and ((direction == 'LONG' and last_close > ema200) or (direction == 'SHORT' and last_close < ema200)):
            ema_details.append("EMA200")

        struct_count = 3 if risk_key == 'HIGH' else (5 if risk_key == 'LOW' else 4)
        struct_ok = hhhl_lhll_structure(candles_4h, count=struct_count, direction=direction)

        min_ema_needed = 1 if risk_key == 'HIGH' else (3 if risk_key == 'LOW' else 2)
        if len(ema_details) >= min_ema_needed and struct_ok:
            passed_rules.append('روند 4h')
            reasons.append(f"روند 4h: بالای/زیر {'، '.join(ema_details)} + ساختار {'HH/HL' if direction=='LONG' else 'LH/LL'} در {struct_count} کندل")

    # ========== Rule 2: روند 1h (برای HIGH ساده‌تر) ==========
    if '1h' in data and '1h' in closes and len(closes['1h']) >= 55:
        candles_1h = data['1h']
        ema21_1h = calculate_ema(closes['1h'], 21)
        ema55_1h = calculate_ema(closes['1h'], 55)

        if risk_key == 'HIGH':
            ema_ok = ((direction == 'LONG' and (last_close > ema21_1h or last_close > ema55_1h)) or
                      (direction == 'SHORT' and (last_close < ema21_1h or last_close < ema55_1h)))
            struct_count_1h = 3
        else:
            ema_ok = ((direction == 'LONG' and last_close > ema21_1h and last_close > ema55_1h) or
                      (direction == 'SHORT' and last_close < ema21_1h and last_close < ema55_1h))
            struct_count_1h = 4

        struct_ok = hhhl_lhll_structure(candles_1h, count=struct_count_1h, direction=direction)

        if ema_ok and struct_ok:
            passed_rules.append('روند 1h')
            reasons.append(f"روند 1h: EMA همسو + ساختار {'HH/HL' if direction=='LONG' else 'LH/LL'} در {struct_count_1h} کندل")

    # ========== Rule 3: EMA21 + ساختار در 30m (برای HIGH فقط EMA21 کافی) ==========
    if '30m' in data and '30m' in closes and len(closes['30m']) >= 21:
        ema21_30m = calculate_ema(closes['30m'], 21)
        price_ok = (direction == 'LONG' and last_close > ema21_30m) or (direction == 'SHORT' and last_close < ema21_30m)

        if risk_key == 'HIGH':
            if price_ok:
                passed_rules.append('EMA21 30m')
                reasons.append("قیمت همسو با EMA21 در 30m")
        else:
            struct_ok_30m = hhhl_lhll_structure(data['30m'], count=3, direction=direction)
            if price_ok and struct_ok_30m:
                passed_rules.append('EMA21 + ساختار 30m')
                reasons.append("قیمت همسو با EMA21 + ساختار در 30m")

    # ========== Rule 4: قدرت کندل 15m — تغییرات پیشنهادی (فقط برای MEDIUM و HIGH) ==========
    if '15m' in data and len(data['15m']) >= 1:
        bs15 = body_strength(data['15m'][-1])
        if risk_key == 'LOW':
            thr = 0.60
        elif risk_key == 'MEDIUM':
            thr = 0.45
        else:  # HIGH
            thr = 0.35
        if bs15 > thr:
            passed_rules.append('کندل قوی 15m')
            reasons.append(f"قدرت کندل 15m = {bs15:.2f} (حد > {thr})")

    # ========== Rule 5: ورود + حجم — تغییرات پیشنهادی (فقط برای MEDIUM و HIGH) ==========
    vol_ok = False
    if '5m' in data and len(data['5m']) >= 10:
        sh, sl = swing_levels(data['5m'], lookback=10)
        level = sh if direction == 'LONG' else sl
        break_ok = broke_level(last_close, level, direction)
        near_ok = is_near(last_close, level, 0.003)

        vol_5m = data['5m'][-1]['v']
        avg_vol_5m = sum(c['v'] for c in data['5m'][-10:]) / 10.0

        if '15m' in data and len(data['15m']) >= 10:
            vol_15m = data['15m'][-1]['v']
            avg_vol_15m = sum(c['v'] for c in data['15m'][-10:]) / 10.0
        else:
            vol_15m = 0.0
            avg_vol_15m = 0.0

        # آستانه حجم بر اساس ریسک (فقط برای MEDIUM و HIGH تغییر)
        if risk_key == 'LOW':
            vol_threshold = 1.3
        elif risk_key == 'MEDIUM':
            vol_threshold = 1.2
        else:  # HIGH
            vol_threshold = 1.1

        # اگر کندل شکست 5m قوی باشد، برای HIGH حجم می‌تواند به 1.0x کاهش یابد
        bs_break_5m = body_strength(data['5m'][-1]) if len(data['5m']) else 0.0
        effective_mult = 1.0 if (risk_key == 'HIGH' and bs_break_5m >= 0.4) else vol_threshold

        vol_ok_5m = vol_5m >= effective_mult * avg_vol_5m
        vol_ok_15m = (avg_vol_15m > 0 and vol_15m >= effective_mult * avg_vol_15m)
        vol_ok = vol_ok_5m or vol_ok_15m

        entry_cond = break_ok or (near_ok and risk_key != 'LOW')
        if entry_cond and vol_ok:
            passed_rules.append('ورود + حجم')
            reasons.append(f"{'شکست' if break_ok else 'نزدیکی'} سطح + حجم ≥{effective_mult:.1f}x")

    # ========== Rule 6: RSI (شدت بر اساس ریسک) ==========
    req_rsi = risk_config['rules'].get('rsi_threshold_count', 3)
    rsi_ok, rsi_count, rsi_vals = rsi_count_ok(closes, direction, req_rsi)
    extra_rsi = sum(1 for v in rsi_vals.values() if (direction == 'LONG' and v > 70) or (direction == 'SHORT' and v < 30))

    if risk_key == 'LOW':
        rsi_condition = (rsi_count >= 4 and extra_rsi >= 2)
    elif risk_key == 'MEDIUM':
        rsi_condition = (rsi_count >= 3 and extra_rsi >= 1)
    else:
        rsi_condition = rsi_count >= 2 or extra_rsi >= 1

    # ========== Rule 7: MACD (شدت؛ شمارش پاک‌سازی‌شده) ==========
    req_macd = risk_config['rules'].get('macd_threshold_count', 3)
    macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, req_macd)

    hist_values = [v[1] for v in macd_vals.values() if v[1] is not None]

    if len(hist_values) >= 10:
        avg_hist_10 = sum(abs(h) for h in hist_values[-10:]) / 10.0
    elif len(hist_values) > 0:
        avg_hist_10 = sum(abs(h) for h in hist_values) / len(hist_values)
    else:
        avg_hist_10 = 1e-6

    multiplier = 1.3 if risk_key == 'LOW' else (1.2 if risk_key == 'MEDIUM' else 1.1)

    extra_macd = 0
    for h in hist_values[-3:]:
        if (direction == 'LONG' and h > avg_hist_10 * multiplier) or (direction == 'SHORT' and h < -avg_hist_10 * multiplier):
            extra_macd += 1

    macd_rule = macd_ok or (extra_macd >= 1)

    # برای HIGH کافیست یکی از RSI یا MACD پاس شود
    if risk_key == 'HIGH':
        if rsi_condition or macd_rule:
            passed_rules.append('مومنتوم (RSI/MACD)')
            reasons.append(f"RSI {rsi_count}/5 + قوی={extra_rsi} یا MACD {macd_count}/5 + شدت={extra_macd}")
    else:
        if rsi_condition:
            passed_rules.append('RSI')
            reasons.append(f"RSI: {rsi_count}/5 همسو + {extra_rsi} خیلی قوی (>70/<30)")
        if macd_rule:
            passed_rules.append('MACD')
            reasons.append(f"MACD: {macd_count}/5 همسو + {extra_macd} شدت قوی")

    # ========== Rule 8: عدم واگرایی (برای HIGH اختیاری) ==========
    div_free = no_divergence(data, closes)
    if risk_key == 'HIGH':
        if div_free:
            passed_rules.append('عدم واگرایی')
            reasons.append("بدون واگرایی در 1h و 4h")
    else:
        if div_free:
            passed_rules.append('عدم واگرایی')
            reasons.append("بدون واگرایی در 1h و 4h")

    # ========== Rule 9: حجم اسپایک + قدرت کندل در 15m ==========
    if '15m' in data and len(data['15m']) >= 10:
        vol_15m = data['15m'][-1]['v']
        avg_vol_15m = sum(c['v'] for c in data['15m'][-10:]) / 10.0
        vol_multiplier = 1.3 if risk_key == 'LOW' else (1.2 if risk_key == 'MEDIUM' else 1.1)
        bs15 = body_strength(data['15m'][-1])
        bs_thr = 0.6 if risk_key == 'LOW' else (0.45 if risk_key == 'MEDIUM' else 0.35)
        if avg_vol_15m > 0 and vol_15m >= vol_multiplier * avg_vol_15m and bs15 > bs_thr:
            passed_rules.append('حجم + کندل 15m')
            reasons.append(f"حجم اسپایک (≥{vol_multiplier}x) + قدرت کندل 15m = {bs15:.2f}")

    # ========== تصمیم نهایی: آستانه‌ها ==========
    passed_count = len(passed_rules)
    if risk_key == 'LOW':
        decision = passed_count >= 7
    elif risk_key == 'MEDIUM':
        decision = passed_count >= 6
    else:
        decision = passed_count >= 5

    return {
        'passed': decision,
        'passed_count': passed_count,
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': risk_config['name'],
    }
