from indicators import calculate_ema, calculate_rsi, calculate_macd

def check_rules_for_level(analysis_data, risk_config, direction):
    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    rules = risk_config['rules']
    passed_rules, reasons = [], []

    # قانون 1: EMA 4h
    if '4h' in closes:
        ema21 = calculate_ema(closes['4h'], 21)
        if ema21 and ((direction=='LONG' and last_close>ema21) or
                      (direction=='SHORT' and last_close<ema21)):
            passed_rules.append('EMA 4h')
            reasons.append("قیمت نسبت به EMA21 مناسب است")

    # قانون 2: EMA 1h
    if '1h' in closes:
        ema21 = calculate_ema(closes['1h'], 21)
        if ema21 and ((direction=='LONG' and last_close>ema21) or
                      (direction=='SHORT' and last_close<ema21)):
            passed_rules.append('EMA 1h')
            reasons.append("قیمت نسبت به EMA21 در 1h مناسب است")

    # قانون 3: RSI
    if '5m' in closes:
        rsi = calculate_rsi(closes['5m'],14)
        if rsi and ((direction=='LONG' and rsi>50) or (direction=='SHORT' and rsi<50)):
            passed_rules.append('RSI')
            reasons.append(f"RSI={rsi:.1f}")

    # قانون 4: MACD
    if '15m' in closes:
        macd = calculate_macd(closes['15m'])
        if macd['macd'] and ((direction=='LONG' and macd['macd']>0) or (direction=='SHORT' and macd['macd']<0)):
            passed_rules.append('MACD')
            reasons.append("MACD همسو")

    # قانون 5: ورود نزدیک به سطح
    if '5m' in closes:
        ema5 = calculate_ema(closes['5m'], 21)
        if ema5 and abs(last_close-ema5)/ema5 <= rules['entry_break_threshold']:
            passed_rules.append('ورود')
            reasons.append("قیمت نزدیک سطح ورود")

    return {
        'passed': len(passed_rules)>=3,  # شرط ساده: حداقل 3 قانون پاس شود
        'passed_count': len(passed_rules),
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': risk_config['name'],
        'emoji': risk_config['emoji']
    }
