# ========== اندیکاتورها و تحلیل ==========
def calculate_ema(prices, period):
    """محاسبه EMA"""
    if not prices or len(prices) < period:
        return None
    try:
        k = 2.0 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = (price - ema) * k + ema
        return ema
    except:
        return None


def calculate_rsi(prices, period=14):
    """محاسبه RSI"""
    if not prices or len(prices) < period + 1:
        return None
    try:
        gains, losses = [], []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        rsi_value = 100.0 - (100.0 / (1.0 + rs))
        return max(0.0, min(100.0, rsi_value))
    except:
        return None


def calculate_macd(prices):
    """محاسبه MACD"""
    if not prices or len(prices) < 26:
        return {'macd': None, 'signal': None, 'histogram': None}
    try:
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
        if len(macd_values) >= 9:
            signal_line = calculate_ema(macd_values, 9)
            histogram = macd_line - signal_line if signal_line else None
        else:
            signal_line = None
            histogram = None
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    except:
        return {'macd': None, 'signal': None, 'histogram': None}


def body_strength(candle):
    """قدرت کندل"""
    if not candle or len(candle) < 5:
        return 0.0
    try:
        open_price, close, high, low = candle[1], candle[2], candle[3], candle[4]
        body = abs(close - open_price)
        total = high - low
        if total == 0:
            return 0.0
        return body / total
    except:
        return 0.0
