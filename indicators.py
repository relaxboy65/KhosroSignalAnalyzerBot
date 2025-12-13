# indicators.py

def calculate_ema(prices, period):
    if not prices or len(prices) < period: return None
    k = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * k + ema
    return ema

def calculate_rsi(prices, period=14):
    if not prices or len(prices) < period + 1: return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(change,0))
        losses.append(max(-change,0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_macd(prices):
    if not prices or len(prices) < 26:
        return {'macd': None, 'signal': None, 'histogram': None}
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    if ema12 is None or ema26 is None:
        return {'macd': None, 'signal': None, 'histogram': None}
    macd_line = ema12 - ema26
    macd_values = []
    for i in range(26, len(prices)):
        ema12_temp = calculate_ema(prices[:i+1], 12)
        ema26_temp = calculate_ema(prices[:i+1], 26)
        if ema12_temp is not None and ema26_temp is not None:
            macd_values.append(ema12_temp - ema26_temp)
    signal_line = calculate_ema(macd_values, 9) if len(macd_values) >= 9 else None
    histogram = macd_line - signal_line if signal_line is not None else None
    return {'macd': macd_line, 'signal': signal_line, 'histogram': histogram}

def body_strength(candle):
    # candle: [ts, open, close, high, low, vol]
    if not candle or len(candle) < 5: return 0.0
    open_price, close, high, low = candle[1], candle[2], candle[3], candle[4]
    body = abs(close - open_price)
    total = high - low
    return body/total if total != 0 else 0.0

# ===== Helpers for rules =====

def is_near(a, b, pct=0.003):
    if a is None or b is None: return False
    return abs(a - b) / b <= pct

def hhhl_lhll_structure(candles, count=4, direction='LONG'):
    # Simple structure check on highs/lows over last `count` candles
    if not candles or len(candles) < count: return False
    highs = [c[3] for c in candles[-count:]]
    lows  = [c[4] for c in candles[-count:]]
    if direction == 'LONG':
        # HHHL: highs increasing, lows higher
        return all(highs[i] >= highs[i-1] for i in range(1, len(highs))) and \
               all(lows[i]  >= lows[i-1]  for i in range(1, len(lows)))
    else:
        # LHLL: highs lower, lows lower
        return all(highs[i] <= highs[i-1] for i in range(1, len(highs))) and \
               all(lows[i]  <= lows[i-1]  for i in range(1, len(lows)))

def swing_levels(candles, lookback=10):
    # Finds recent swing high/low using simple pivot logic
    if not candles or len(candles) < lookback: return None, None
    highs = [c[3] for c in candles[-lookback:]]
    lows  = [c[4] for c in candles[-lookback:]]
    swing_high = max(highs)
    swing_low  = min(lows)
    return swing_high, swing_low

def broke_level(price, level, direction):
    if price is None or level is None: return False
    return (direction == 'LONG' and price > level) or (direction == 'SHORT' and price < level)

def rsi_count_ok(all_closes, direction, required):
    tfs = ['5m','15m','30m','1h','4h']
    count = 0
    values = {}
    for tf in tfs:
        if tf in all_closes:
            rsi = calculate_rsi(all_closes[tf],14)
            if rsi is not None:
                values[tf] = rsi
                if (direction=='LONG' and rsi > 50) or (direction=='SHORT' and rsi < 50):
                    count += 1
    return count >= required, count, values

def macd_count_ok(all_closes, direction, required):
    tfs = ['5m','15m','30m','1h','4h']
    count = 0
    values = {}
    for tf in tfs:
        if tf in all_closes:
            macd = calculate_macd(all_closes[tf])
            m, s, h = macd['macd'], macd['signal'], macd['histogram']
            if m is not None and s is not None and h is not None:
                values[tf] = (m, s, h)
                ok = (direction=='LONG' and m>0 and h>0) or (direction=='SHORT' and m<0 and h<0)
                if ok: count += 1
    return count >= required, count, values

def no_divergence(candles, closes, tf_list=('1h','4h')):
    # Minimal check: last price delta and RSI delta in same direction => no divergence
    for tf in tf_list:
        if tf in closes and len(closes[tf]) >= 16:
            rsi1 = calculate_rsi(closes[tf][-16:],14)
            rsi2 = calculate_rsi(closes[tf][-15:],14)  # shifted one
            p1 = closes[tf][-1] - closes[tf][-2]
            if rsi1 is None or rsi2 is None: return False
            rsi_delta = (rsi2 - rsi1)
            if (p1 > 0 and rsi_delta < 0) or (p1 < 0 and rsi_delta > 0):
                return False
    return True
