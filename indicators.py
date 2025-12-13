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
        if ema12_temp and ema26_temp:
            macd_values.append(ema12_temp - ema26_temp)
    signal_line = calculate_ema(macd_values, 9) if len(macd_values) >= 9 else None
    histogram = macd_line - signal_line if signal_line else None
    return {'macd': macd_line, 'signal': signal_line, 'histogram': histogram}

def body_strength(candle):
    if not candle or len(candle) < 5: return 0.0
    open_price, close, high, low = candle[1], candle[2], candle[3], candle[4]
    body = abs(close - open_price)
    total = high - low
    return body/total if total != 0 else 0.0
