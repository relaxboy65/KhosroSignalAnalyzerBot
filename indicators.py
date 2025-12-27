import math

# ===== EMA =====
def ema_series(prices, period):
    if len(prices) < period:
        return [None] * len(prices)
    k = 2.0 / (period + 1)
    ema_vals = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema_vals.append(price * k + ema_vals[-1] * (1 - k))
    return [None] * (period - 1) + ema_vals

def calculate_ema(prices, period):
    series = ema_series(prices, period)
    return series[-1] if series else None

# ===== RSI =====
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
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

# ===== MACD =====
def calculate_macd(prices, fast=12, slow=26, signal_period=9):
    if len(prices) < slow + signal_period:
        return {'macd': None, 'signal': None, 'histogram': None}
    ema_fast = ema_series(prices, fast)
    ema_slow = ema_series(prices, slow)
    macd_line = [(f - s) if f and s else None for f, s in zip(ema_fast, ema_slow)]
    valid_macd = [m for m in macd_line if m is not None]
    if len(valid_macd) < signal_period:
        return {'macd': macd_line[-1], 'signal': None, 'histogram': None}
    signal_full = ema_series(valid_macd, signal_period)
    signal_series = [None] * (len(macd_line) - len(signal_full)) + signal_full
    histogram = [m - s if m and s else None for m, s in zip(macd_line, signal_series)]
    return {'macd': macd_line[-1], 'signal': signal_series[-1], 'histogram': histogram[-1]}

# ===== ATR =====
def calculate_atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    tr_list = []
    for i in range(1, len(candles)):
        high, low, prev_close = candles[i]['h'], candles[i]['l'], candles[i-1]['c']
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    if len(tr_list) < period:
        return None
    atr = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 6)

# ===== Body Strength =====
def body_strength(candle):
    open_p, close_p, high, low = candle['o'], candle['c'], candle['h'], candle['l']
    body = abs(close_p - open_p)
    total_range = high - low if high > low else 0.000001
    return body / total_range
# ===== ADX =====
def calculate_adx(candles, period=14):
    if len(candles) < period + 1:
        return None
    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(candles)):
        high, low = candles[i]['h'], candles[i]['l']
        prev_high, prev_low, prev_close = candles[i-1]['h'], candles[i-1]['l'], candles[i-1]['c']
        up_move = high - prev_high
        down_move = prev_low - low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    atr = sum(tr_list[:period]) / period
    plus_di = 100 * (sum(plus_dm[:period]) / atr) if atr else 0
    minus_di = 100 * (sum(minus_dm[:period]) / atr) if atr else 0
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) != 0 else 0
    return round(dx, 2)

# ===== CCI =====
def calculate_cci(candles, period=20):
    if len(candles) < period:
        return None
    tp = [(c['h'] + c['l'] + c['c']) / 3 for c in candles]
    sma = sum(tp[-period:]) / period
    mean_dev = sum(abs(x - sma) for x in tp[-period:]) / period
    if mean_dev == 0:
        return 0
    cci = (tp[-1] - sma) / (0.015 * mean_dev)
    return round(cci, 2)

# ===== Parabolic SAR =====
def calculate_sar(candles, step=0.02, max_step=0.2):
    if len(candles) < 2:
        return None
    # ساده‌سازی: فقط آخرین مقدار SAR
    prev_high, prev_low = candles[-2]['h'], candles[-2]['l']
    curr_high, curr_low = candles[-1]['h'], candles[-1]['l']
    ep = curr_high if curr_high > prev_high else curr_low
    sar = prev_low + step * (ep - prev_low)
    return round(sar, 4)

# ===== Stochastic Oscillator =====
def calculate_stochastic(candles, period=14, smooth_k=3, smooth_d=3):
    if len(candles) < period:
        return None, None
    closes = [c['c'] for c in candles]
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    highest_high = max(highs[-period:])
    lowest_low = min(lows[-period:])
    k = 100 * (closes[-1] - lowest_low) / (highest_high - lowest_low) if highest_high != lowest_low else 0
    k_series = [k]
    d = sum(k_series[-smooth_d:]) / smooth_d
    return round(k, 2), round(d, 2)
