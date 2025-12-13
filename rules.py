# rules.py
from indicators import (
    calculate_ema, calculate_rsi, calculate_macd, body_strength,
    is_near, hhhl_lhll_structure, swing_levels, broke_level,
    rsi_count_ok, macd_count_ok, no_divergence
)

def check_rules_for_level(analysis_data, risk_config, direction):
    last_close = analysis_data['last_close']
    closes = analysis_data['closes']
    data = analysis_data['data']  # raw candles with OHLCV
    passed_rules = []
    reasons = []


    # Risk profile parameters
    risk_key = risk_config['key']
    # Handle limited 4h candles: fallback when EMA200 is unavailable
    have_4h_ema200 = ('4h' in closes and len(closes['4h']) >= 200)

    # Rule 1: 4h trend (EMA + structure)
    if '4h' in data:
        candles_4h = data['4h']
        ema21_4h = calculate_ema(closes['4h'],21)
        ema55_4h = calculate_ema(closes['4h'],55)
        ema200_4h = calculate_ema(closes['4h'],200) if have_4h_ema200 else None
        struct_count = 5 if risk_key=='LOW' else 4

        def above_below(emaval):
            if emaval is None: return False
            return (direction=='LONG' and last_close > emaval) or (direction=='SHORT' and last_close < emaval)

        cond_low = (above_below(ema21_4h) and above_below(ema55_4h) and (above_below(ema200_4h) if ema200_4h is not None else True))
        cond_med = (above_below(ema21_4h) and above_below(ema55_4h))
        cond_high = ((above_below(ema21_4h)) or is_near(last_close, ema21_4h, 0.003))

        cond_ema = cond_low if risk_key=='LOW' else cond_med if risk_key=='MEDIUM' else cond_high
        cond_struct = hhhl_lhll_structure(candles_4h, count=struct_count, direction=direction)

        if cond_ema and cond_struct:
            passed_rules.append('روند 4h')
            reasons.append(f"4h: EMA21/55{('/200' if risk_key=='LOW' and ema200_4h else '')} همسو + ساختار {'HHHL' if direction=='LONG' else 'LHLL'}")

    # Rule 2: 1h trend (EMA + structure)
    if '1h' in data:
        candles_1h = data['1h']
        ema21_1h = calculate_ema(closes['1h'],21)
        ema55_1h = calculate_ema(closes['1h'],55)

        def above_below_1h(emaval):
            if emaval is None: return False
            return (direction=='LONG' and last_close > emaval) or (direction=='SHORT' and last_close < emaval)

        if risk_key=='LOW':
            cond = above_below_1h(ema21_1h) and above_below_1h(ema55_1h)
        elif risk_key=='MEDIUM':
            cond = above_below_1h(ema21_1h) or above_below_1h(ema55_1h)
        else:
            cond = above_below_1h(ema21_1h) or above_below_1h(ema55_1h) or \
                   is_near(last_close, ema21_1h, 0.003) or is_near(last_close, ema55_1h, 0.003)

        cond_struct = hhhl_lhll_structure(candles_1h, count=4, direction=direction)
        if cond and cond_struct:
            passed_rules.append('روند 1h')
            reasons.append(f"1h: EMA{('21/55' if risk_key=='LOW' else '21 یا 55')} + ساختار {'HHHL' if direction=='LONG' else 'LHLL'}")

    # Rule 3: 30m pullback/rally around EMA21
    if '30m' in closes and '30m' in data:
        ema21_30m = calculate_ema(closes['30m'],21)
        near_30 = is_near(last_close, ema21_30m, 0.003)
        if risk_key=='LOW':
            cond = (direction=='LONG' and last_close > ema21_30m) or \
                   (direction=='SHORT' and last_close < ema21_30m)
        else:
            cond = ((direction=='LONG' and (last_close > ema21_30m or near_30)) or
                    (direction=='SHORT' and (last_close < ema21_30m or near_30)))
        if cond:
            passed_rules.append('۳۰m پولبک/رالی')
            reasons.append("30m: همسو با EMA21 یا نزدیک آن")

    # Rule 4: 15m strong/medium candle by body strength
    if '15m' in data and len(data['15m']) >= 1:
        bs = body_strength(data['15m'][-1])
        thr = 0.6 if risk_key=='LOW' else 0.48 if risk_key=='MEDIUM' else 0.35
        if bs > thr:
            passed_rules.append('کندل 15m')
            reasons.append(f"15m: قدرت کندل {bs:.2f} > {thr}")

    # Rule 5: 5m breakout + volume + candle strength
    if '5m' in data and len(data['5m']) >= 10:
        swing_high, swing_low = swing_levels(data['5m'], lookback=10)
        price_break = broke_level(last_close, swing_high if direction=='LONG' else swing_low, direction)
        close_candle = data['5m'][-1]
        vol = close_candle[5] if len(close_candle) >= 6 else 0.0
        avg_vol = sum([c[5] for c in data['5m'][-10:] if len(c) >= 6]) / 10.0
        bs5 = body_strength(close_candle)

        vol_ok = vol >= 1.2 * avg_vol  # high volume heuristic
        bs_thr = 0.6 if risk_key=='LOW' else 0.48
        near_ok = is_near(last_close, swing_high if direction=='LONG' else swing_low, 0.003)

        if risk_key=='LOW':
            cond = price_break and vol_ok and (bs5 > bs_thr)
        else:
            cond = (price_break or near_ok) and vol_ok and (bs5 > bs_thr)
        if cond:
            passed_rules.append('شکست 5m + حجم')
            reasons.append(f"5m: {'شکست' if price_break else 'نزدیک شکست'} با حجم بالا و قدرت {bs5:.2f}")

    # Rule 6: RSI across timeframes
    req = 5 if risk_key=='LOW' else 4 if risk_key=='MEDIUM' else 3
    rsi_ok, rsi_count, rsi_values = rsi_count_ok(closes, direction, req)
    if rsi_ok:
        passed_rules.append('RSI چند تایم‌فریم')
        reasons.append(f"RSI: {rsi_count}/5 تایم‌فریم {'>' if direction=='LONG' else '<'} 50")

    # Rule 7: MACD across timeframes (+ histogram color)
    reqm = 5 if risk_key=='LOW' else 4 if risk_key=='MEDIUM' else 3
    macd_ok, macd_count, macd_values = macd_count_ok(closes, direction, reqm)
    if macd_ok:
        passed_rules.append('MACD چند تایم‌فریم')
        reasons.append(f"MACD: {macd_count}/5 تایم‌فریم همسو با {'سبز' if direction=='LONG' else 'قرمز'}")

    # Rule 8: No divergence on main TFs
    if no_divergence(data, closes, tf_list=('1h','4h')):
        passed_rules.append('عدم واگرایی')
        reasons.append("بدون واگرایی در 1h و 4h")

    # Rule 9: Entry rule (swing break/near)
    if '5m' in data:
        sh, sl = swing_levels(data['5m'], lookback=10)
        break_ok = broke_level(last_close, sh if direction=='LONG' else sl, direction)
        near_ok = is_near(last_close, sh if direction=='LONG' else sl, 0.003)
        if risk_key=='LOW':
            cond = break_ok
        else:
            cond = break_ok or near_ok
        if cond:
            passed_rules.append('قانون ورود')
            reasons.append(f"ورود: {'شکست کامل' if break_ok else 'نزدیک شکست (±0.3%)'}")

    # Decision: require all 9 rules (or allow minimal due to 4h EMA200 unavailable?)
    # Strict per table: all must pass. If 4h EMA200 unavailable, Rule1 still counts if EMA21/55 + structure holds.
    passed_count = len(passed_rules)
    decision = (passed_count == 9)

    return {
        'passed': decision,
        'passed_count': passed_count,
        'passed_rules': passed_rules,
        'reasons': reasons,
        'risk_name': risk_config['name'],
        'emoji': risk_config['emoji']
    }
