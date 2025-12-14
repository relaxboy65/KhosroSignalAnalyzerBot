# indicators.py
import math

# ===== EMA (سری کامل + آخرین مقدار) =====
def ema_series(prices, period):
    """محاسبه سری کامل EMA"""
    if len(prices) < period:
        return [None] * len(prices)
    k = 2.0 / (period + 1)
    ema_vals = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema_vals.append(price * k + ema_vals[-1] * (1 - k))
    return [None] * (period - 1) + ema_vals

def calculate_ema(prices, period):
    """آخرین مقدار EMA (سازگار با کد قدیمی)"""
    series = ema_series(prices, period)
    return series[-1] if series else None

# ===== RSI =====
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    if avg_loss == 0:
        return 100.0
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

# ===== MACD با سری کامل + مقدار آخر =====
def calculate_macd(prices, fast=12, slow=26, signal_period=9):
    if len(prices) < slow + signal_period:
        return {
            'macd': None, 'signal': None, 'histogram': None,
            'macd_series': [], 'signal_series': [], 'hist_series': []
        }

    ema_fast = ema_series(prices, fast)
    ema_slow = ema_series(prices, slow)

    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)

    # سیگنال فقط روی مقادیر معتبر MACD
    valid_macd = [m for m in macd_line if m is not None]
    if len(valid_macd) < signal_period:
        signal_series = [None] * len(macd_line)
        histogram = [None] * len(macd_line)
    else:
        signal_full = ema_series(valid_macd, signal_period)
        padding = len(macd_line) - len(signal_full)
        signal_series = [None] * padding + signal_full
        histogram = [m - s if m is not None and s is not None else None 
                     for m, s in zip(macd_line, signal_series)]

    return {
        'macd': macd_line[-1],
        'signal': signal_series[-1],
        'histogram': histogram[-1],
        'macd_series': macd_line,
        'signal_series': signal_series,
        'hist_series': histogram
    }

# ===== ATR (Average True Range) =====
def calculate_atr(candles, period=14):
    """candles: لیست از دیکشنری با کلیدهای o, h, l, c"""
    if len(candles) < period + 1:
        return None
    
    tr_list = []
    for i in range(1, len(candles)):
        high = candles[i]['h']
        low = candles[i]['l']
        prev_close = candles[i-1]['c']
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        tr_list.append(tr)
    
    if len(tr_list) < period:
        return None
    
    atr = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period
    
    return round(atr, 6)

# ===== Body Strength =====
def body_strength(candle):
    """candle: دیکشنری با o, c, h, l یا لیست [ts, o, c, h, l, v]"""
    if isinstance(candle, list):
        open_p, close_p, high, low = candle[1], candle[2], candle[3], candle[4]
    else:
        open_p, close_p, high, low = candle['o'], candle['c'], candle['h'], candle['l']
    
    body = abs(close_p - open_p)
    total_range = high - low if high > low else 0.000001
    return body / total_range

# ===== Swing High/Low =====
def swing_levels(candles, lookback=10):
    """بازگرداندن آخرین Swing High و Swing Low در lookback کندل"""
    if len(candles) < lookback:
        return None, None
    
    recent = candles[-lookback:]
    highs = [c['h'] for c in recent[:-1]]  # بدون آخرین کندل
    lows = [c['l'] for c in recent[:-1]]
    
    swing_high = max(highs) if highs else None
    swing_low = min(lows) if lows else None
    
    return swing_high, swing_low

# ===== چک نزدیکی قیمت به سطح =====
def is_near(price, level, threshold=0.003):
    if price is None or level is None:
        return False
    return abs(price - level) / level <= threshold

# ===== ساختار HH/HL یا LH/LL =====
def hhhl_lhll_structure(candles, count=5, direction='LONG'):
    if len(candles) < count:
        return False
    recent = candles[-count:]
    if direction == 'LONG':
        return all(recent[i]['high'] > recent[i-1]['high'] and recent[i]['low'] > recent[i-1]['low'] for i in range(1, count))
    else:  # SHORT
        return all(recent[i]['high'] < recent[i-1]['high'] and recent[i]['low'] < recent[i-1]['low'] for i in range(1, count))

# ===== شکست سطح =====
def broke_level(current_price, level, direction):
    if current_price is None or level is None:
        return False
    return (direction == 'LONG' and current_price > level) or (direction == 'SHORT' and current_price < level)

# ===== شمارش RSI بالای/زیر 50 =====
def rsi_count_ok(all_closes, direction, required):
    tfs = ['5m','15m','30m','1h','4h']
    count = 0
    values = {}
    for tf in tfs:
        if tf in all_closes and len(all_closes[tf]) >= 15:
            r = calculate_rsi(all_closes[tf])
            if r is not None:
                values[tf] = round(r, 2)
                if (direction == 'LONG' and r > 50) or (direction == 'SHORT' and r < 50):
                    count += 1
    return count >= required, count, values

# ===== شمارش MACD همسو =====
def macd_count_ok(all_closes, direction, required):
    tfs = ['5m','15m','30m','1h','4h']
    count = 0
    values = {}
    for tf in tfs:
        if tf in all_closes and len(all_closes[tf]) >= 35:
            macd = calculate_macd(all_closes[tf])
            m, h = macd['macd'], macd['histogram']
            if m is not None and h is not None:
                values[tf] = (round(m, 6), round(h, 6))
                ok = (direction == 'LONG' and m > 0 and h > 0) or (direction == 'SHORT' and m < 0 and h < 0)
                if ok:
                    count += 1
    return count >= required, count, values

# ===== واگرایی ساده (بهبودیافته) =====
def no_divergence(candles, closes, tf_list=('1h','4h')):
    for tf in tf_list:
        if tf in closes and len(closes[tf]) >= 30:
            prices = closes[tf]
            macd_obj = calculate_macd(prices)
            hist = macd_obj['histogram']
            if hist is None:
                continue
            # چک ساده: اگر قیمت بالا بره ولی هیستوگرام پایین بیاد → واگرایی
            lookback = 20
            if len(prices) < lookback:
                continue
            price_change = prices[-1] - prices[-lookback]
            hist_change = macd_obj['hist_series'][-1] - macd_obj['hist_series'][-lookback] if macd_obj['hist_series'][-lookback] is not None else 0
            if (price_change > 0 and hist_change < 0) or (price_change < 0 and hist_change > 0):
                return False
    return True
