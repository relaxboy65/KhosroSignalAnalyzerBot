from indicators import calculate_ema, calculate_rsi, calculate_macd

def check_rules_for_level(analysis_data, risk_config, direction):
    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    rules = risk_config['rules']
    passed_rules, reasons = [], []

    # قانون نمونه: EMA 4h
    if '4h' in closes:
        ema21 = calculate_ema(closes['4h'], 21)
        if ema21 and ((direction=='LONG' and last_close>ema21) or
                      (direction=='SHORT' and last_close<ema21)):
            passed_rules.append('EMA 4h')
            reasons.append(f"قیمت نسبت به EMA21 مناسب است")

    # RSI
    if '5m' in closes:
        rsi = calculate_rsi(closes['5m'],14)
        if rsi and ((direction=='LONG' and rsi>50) or (direction=='SHORT' and rsi<50)):
            passed_rules.append('RSI')
            reasons.append(f"RSI={rsi:.1f}")

    # MACD
    if '15m' in closes:
        macd = calculate_macd(closes['15m'])
        if macd['macd'] and ((direction=='LONG' and macd['macd']>0) or (direction=='SHORT' and macd['macd']<0)):
            passed_rules.append('MACD')
            reasons.append("MACD همسو")

    return {
        'passed': len(passed_rules)>=3,  # شرط ساده: حداقل 3 قانون پاس شود
        'passed_count': len(passed_rules),
        'passed_rules': passed_rules,
        'reasons': reasons,
