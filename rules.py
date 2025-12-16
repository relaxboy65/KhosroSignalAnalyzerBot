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

    # Rule 1: روند 4h (EMA + ساختار)
    if '4h' in data:
        candles_4h = data['4h']
        ema21 = calculate_ema(closes['4h'], 21)
        ema55 = calculate_ema(closes['4h'], 55)
        ema200 = calculate_ema(closes['4h'], 200) if len(closes['4h']) >= 200 else None

        ema_details = []
        if (direction == 'LONG' and last_close > ema21) or (direction == 'SHORT' and last_close < ema21):
            ema_details.append("EMA21")
        if (direction == 'LONG' and last_close > ema55) or (direction == 'SHORT' and last_close < ema55):
            ema_details.append("EMA55")
        if ema200 and ((direction == 'LONG' and last_close > ema200) or (direction == 'SHORT' and last_close < ema200)):
            ema_details.append("EMA200")

        struct_count = 5 if risk_key == 'LOW' else 4 if risk_key == 'MEDIUM' else 3
        struct_ok = hhhl_lhll_structure(candles_4h, count=struct_count, direction=direction)

        if len(ema_details) >= (3 if risk_key=='LOW' else 2 if risk_key=='MEDIUM' else 1) and struct_ok:
            passed_rules.append('روند 4h')
            reasons.append(f"روند 4h: بالای/زیر {'، '.join(ema_details)} + ساختار {'HH/HL' if direction=='LONG' else 'LH/LL'} در {struct_count} کندل")

    # Rule 2: روند 1h
    if '1h' in data:
        candles_1h = data['1h']
        ema21_1h = calculate_ema(closes['1h'], 21)
        ema55_1h = calculate_ema(closes['1h'], 55)

        ema_ok = ((direction == 'LONG' and last_close > ema21_1h and last_close > ema55_1h) or
                  (direction == 'SHORT' and last_close < ema21_1h and last_close < ema55_1h))

        struct_count = 4 if risk_key != 'HIGH' else 3
        struct_ok = hhhl_lhll_structure(candles_1h, count=struct_count, direction=direction)

        if ema_ok and struct_ok:
            passed_rules.append('روند 1h')
            reasons.append(f"روند 1h: بالای/زیر EMA21 و EMA55 + ساختار {'HH/HL' if direction=='LONG' else 'LH/LL'}")

    # Rule 3: EMA21 + ساختار در 30m
    if '30m' in data:
        ema21_30m = calculate_ema(closes['30m'], 21)
        price_ok = (direction == 'LONG' and last_close > ema21_30m) or (direction == 'SHORT' and last_close < ema21_30m)
        struct_ok = hhhl_lhll_structure(data['30m'], count=3, direction=direction)

        if price_ok and struct_ok:
            passed_rules.append('EMA21 + ساختار 30m')
            reasons.append(f"قیمت {'بالای' if direction=='LONG' else 'زیر'} EMA21 + ساختار در 30m")

    # Rule 4: قدرت کندل 15m (۵٪ آسان‌تر برای ریسک بالا)
    if '15m' in data and len(data['15m']) >= 1:
        bs = body_strength(data['15m'][-1])
        thr = risk_config['rules']['candle_15m_strength']
        if risk_key == 'MEDIUM':
            thr = 0.45
        if risk_key == 'HIGH':
            thr = 0.35  # آسان‌تر از 0.4
        if bs > thr:
            passed_rules.append('کندل قوی 15m')
            reasons.append(f"قدرت کندل 15m = {bs:.2f} (حد > {thr})")

    # Rule 5: ورود + حجم (۵٪ آسان‌تر)
    vol_ok = False
    entry_ok = False

    if '5m' in data and len(data['5m']) >= 10:
        sh, sl = swing_levels(data['5m'], lookback=10)
        level = sh if direction == 'LONG' else sl
        break_ok = broke_level(last_close, level, direction)
        near_ok = is_near(last_close, level, 0.003)

        vol_5m = data['5m'][-1]['v']
        avg_vol_5m = sum(c['v'] for c in data['5m'][-10:]) / 10.0
        vol_ok_5m = vol_5m >= 1.2 * avg_vol_5m  # آسان‌تر از 1.3

        if '15m' in data and len(data['15m']) >= 10:
            vol_15m = data['15m'][-1]['v']
            avg_vol_15m = sum(c['v'] for c in data['15m'][-10:]) / 10.0
            vol_ok_15m = vol_15m >= 1.2 * avg_vol_15m  # آسان‌تر از 1.25
            vol_ok = vol_ok_5m or vol_ok_15m
        else:
            vol_ok = vol_ok_5m

        entry_cond = break_ok or (near_ok and risk_key != 'LOW')
        if entry_cond and vol_ok:
            passed_rules.append('ورود + حجم')
            reasons.append(f"{'شکست' if break_ok else 'نزدیکی'} سطح با حجم بالا")

    # Rule 6: RSI (با شدت)
    req = risk_config['rules']['rsi_threshold_count']
    rsi_ok, rsi_count, rsi_vals = rsi_count_ok(closes, direction, req)
    extra_rsi = sum(1 for v in rsi_vals.values() if (direction=='LONG' and v > 70) or (direction=='SHORT' and v < 30))
    if rsi_ok or (rsi_count >= req - 1 and extra_rsi >= 1):
        passed_rules.append('RSI')
        reasons.append(f"RSI: {rsi_count}/5 همسو + {extra_rsi} خیلی قوی (>70/<30)")

    # Rule 7: MACD (با شدت هیستوگرام — ۵٪ آسان‌تر)
    reqm = risk_config['rules']['macd_threshold_count']
    macd_ok, macd_count, macd_vals = macd_count_ok(closes, direction, reqm)
    extra_macd = 0
    hist_values = [v[1] for v in macd_vals.values() if v[1] is not None]
    if len(hist_values) >= 5:
        avg_hist = sum(abs(h) for h in hist_values[-5:]) / 5.0
        for h in hist_values[-3:]:
            if (direction=='LONG' and h > avg_hist * 1.1) or (direction=='SHORT' and h < -avg_hist * 1.1):
                extra_macd += 1
    if macd_ok or (macd_count >= reqm - 1 and extra_macd >= 1):
        passed_rules.append('MACD')
        reasons.append(f"MACD: {macd_count}/5 همسو + {extra_macd} هیستوگرام قوی")

    # Rule 8: عدم واگرایی
    if no_divergence(data, closes):
        passed_rules.append('عدم واگرایی')
        reasons.append("بدون واگرایی در 1h و 4h")

    # Rule 9: حجم اسپایک + قدرت کندل در 15m (۵٪ آسان‌تر)
    if '15m' in data and len(data['15m']) >= 10:
        vol_15m = data['15m'][-1]['v']
        avg_vol_15m = sum(c['v'] for c in data['15m'][-10:]) / 10.0
        bs15 = body_strength(data['15m'][-1])
        if vol_15m >= 1.2 * avg_vol_15m and bs15 > 0.4:  # آسان‌تر از 1.25 و 0.45
            passed_rules.append('حجم + کندل 15m')
            reasons.append(f"حجم اسپایک + قدرت کندل 15m = {bs15:.2f}")

    passed_count = len(passed_rules)

    # آستانه‌ها (ریسک بالا ۵٪ آسان‌تر)
    if risk_key == 'LOW':
        decision = passed_count >= 7
    elif risk_key == 'MEDIUM':
        decision = passed_count >= 7
    else:  # HIGH
        decision = passed_count >= 5   # تغییر اصلی برای ۵٪ آسان‌تر

    return {
        'passed': decision,
        'passed_count': passed_count,
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': risk_config['name'],
    }
