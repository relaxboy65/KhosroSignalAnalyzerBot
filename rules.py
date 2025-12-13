def check_rules_for_level(analysis_data, risk_config, direction):
    """بررسی قوانین برای یک سطح ریسک"""
    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    rules = risk_config['rules']
    passed_rules, reasons = [], []

    # مثال ساده: EMA 4h
    if '4h' in closes:
        ema21 = calculate_ema(closes['4h'], 21)
        if ema21 and ((direction=='LONG' and last_close>ema21) or
                      (direction=='SHORT' and last_close<ema21)):
            passed_rules.append('EMA 4h'); reasons.append('قیمت نسبت به EMA21 مناسب است')

    # RSI
    if '5m' in closes:
        rsi = calculate_rsi(closes['5m'],14)
        if rsi and ((direction=='LONG' and rsi>50) or (direction=='SHORT' and rsi<50)):
            passed_rules.append('RSI'); reasons.append(f'RSI={rsi:.1f}')

    return {
        'passed': len(passed_rules)>=2,
        'passed_count': len(passed_rules),
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': risk_config['name'],
        'emoji': risk_config['emoji']
    }
