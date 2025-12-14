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

    # Rule 4: قدرت کندل 15m
    if '15m' in data and len(data['15m']) >= 1:
        bs = body_strength(data['15m'][-1])
        thr = risk_config['rules']['candle_15m_strength']
        if bs > thr:
            passed_rules.append('کندل 15m')
            reasons.append(f"قدرت کندل 15m = {bs:.2f}")

    # Rule 5: شکست 5m + حجم
    if '5m' in data and len(data['5m']) >= 10:
        sh, sl = swing_levels(data['5m'], lookback=10)
        price_break = broke_level(last_close, sh if direction=='LONG' else sl, direction)
        vol = data['5m'][-1]['v']
        avg_vol = sum([c['v'] for c in data['5m'][-10:]]) / 10.0
        bs5 = body_strength(data['5m'][-1])
        vol_ok = vol >= 1.2 * avg_vol
        if price_break and vol_ok and bs5 > risk_config['rules']['candle_5m_strength']:
            passed_rules.append('شکست 5m + حجم')
            reasons.append("شکست سطح در 5m با حجم بالا")

    # Rule 6: RSI
    req = risk_config['rules']['rsi_threshold_count']
    rsi_ok, rsi_count, _ = rsi_count_ok(closes, direction, req)
    if rsi_ok:
        passed_rules.append('RSI')
        reasons.append(f"RSI: {rsi_count}/5 تایم‌فریم همسو")

    # Rule 7: MACD
    reqm = risk_config['rules']['macd_threshold_count']
    macd_ok, macd_count, _ = macd_count_ok(closes, direction, reqm)
    if macd_ok:
        passed_rules.append('MACD')
        reasons.append(f"MACD: {macd_count}/5 تایم‌فریم همسو")

    # Rule 8: عدم واگرایی
    if no_divergence(data, closes, tf_list=('1h','4h')):
        passed_rules.append('عدم واگرایی')
        reasons.append("بدون واگرایی در 1h و 4h")

    passed_count = len(passed_rules)
    decision = passed_count >= 6 if risk_key=='HIGH' else passed_count >= 7 if risk_key=='MEDIUM' else passed_count >= 9

    return {
        'passed': decision,
        'passed_count': passed_count,
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': risk_config['name'],
    }
