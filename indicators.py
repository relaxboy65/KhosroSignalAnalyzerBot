# indicators.py
import math

# ===== EMA =====
def _ema_series(prices, period):
    if not prices or len(prices) < period:
        return [None] * len(prices)
    k = 2.0 / (period + 1)
    out = [None] * (period - 1)
    ema = sum(prices[:period]) / period
    out.append(ema)
    for price in prices[period:]:
        ema = (price - ema) * k + ema
        out.append(ema)
    return out

def calculate_ema(prices, period):
    # سازگار با استفاده فعلی: آخرین EMA را برمی‌گرداند
    if not prices or len(prices) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * k + ema
    return ema

# ===== RSI =====
def calculate_rsi(prices, period=14):
    if not prices or len(prices) < period + 1:
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
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

# ===== MACD (با سری کامل، خروجی آخر سازگار با کد فعلی) =====
def calculate_macd(prices, fast=12, slow=26, signal=9):
    if not prices or len(prices) < slow:
        return {'macd': None, 'signal': None, 'histogram': None}
    ema_fast = _ema_series(prices, fast)
    ema_slow = _ema_series(prices, slow)
    macd_line = [None if ef is None or es is None else (ef - es) for ef, es in zip(ema_fast, ema_slow)]
    # ساخت سری سیگنال فقط روی مقادیر معتبر
    valid_macd = [m for m in macd_line if m is not None]
    if len(valid_macd) < signal:
        return {'macd': macd_line[-1], 'signal': None, 'histogram': None}
    signal_series = _ema_series(valid_macd, signal)
    signal_last = signal_series[-1]
    hist_last = macd_line[-1] - signal_last if (macd_line[-1] is not None and signal_last is not None) else None
    return {'macd': macd_line[-1], 'signal': signal_last, 'histogram': hist_last}

# ===== ATR برای مدیریت ریسک =====
def calculate_atr(candles, period=14):
    # candles: [[ts, open, close, high, low, vol], ...]
    if not candles or len(candles) < period + 1:
        return None
    trs = []
    prev_close = candles[0][2]
    for c in candles:
        high = c[3]; low = c[4]; close = c[2]
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)
        prev_close = close
    first_atr = sum(trs[:period]) / period
    atr_val = first_atr
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val

# ===== قدرت کندل =====
def body_strength(candle):
    # candle: [ts, open, close, high, low, vol] با ترتیب استفاده‌شده در پروژه
    if not candle or len(candle) < 5:
        return 0.0
    open_price, close, high, low = candle[1], candle[2], candle[3], candle[4]
    body = abs(close - open_price)
    total = high - low
    return body / total if total != 0 else 0.0

# ===== Helpers for rules (حفظ و کمی بهبود) =====
def is_near(a, b, pct=0.003):
    if a is None or b is None:
        return False
    return abs(a - b) / b <= pct

def hhhl_lhll_structure(candles, count=4, direction='LONG'):
    # Simple structure check on highs/lows over last `count` candles
    if not candles or len(candles) < count:
        return False
    highs = [c[3] for c in candles[-count:]]
    lows  = [c[4] for c in candles[-count:]]
    if direction == 'LONG':
        return all(highs[i] >= highs[i - 1] for i in range(1, len(highs))) and \
               all(lows[i]  >= lows[i - 1]  for i in range(1, len(lows)))
    else:
        return all(highs[i] <= highs[i - 1] for i in range(1, len(highs))) and \
               all(lows[i]  <= lows[i - 1]  for i in range(1, len(lows)))

def swing_levels(candles, lookback=10):
    if not candles or len(candles) < lookback:
        return None, None
    highs = [c[3] for c in candles[-lookback:]]
    lows  = [c[4] for c in candles[-lookback:]]
    swing_high = max(highs)
    swing_low  = min(lows)
    return swing_high, swing_low

def broke_level(price, level, direction):
    if price is None or level is None:
        return False
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

# ===== واگرایی پیشرفته (pivot-based ساده و سازگار) =====
def no_divergence(candles, closes, tf_list=('1h','4h')):
    # جایگزین قبلی: اگر واگرایی آشکار نباشد → True
    for tf in tf_list:
        if tf in closes and len(closes[tf]) >= 40:
            prices = closes[tf]
            macd_obj = calculate_macd(prices)
            osc = macd_obj['histogram']
            if osc is None:
                continue
            # پنجره بررسی
            lookback = 20
            p_slice = prices[-lookback:]
            # چون هیستوگرام لحظه‌ای است، برای ارزیابی ساده از قیمت و تغییر RSI استفاده می‌کنیم
            rsi1 = calculate_rsi(prices[-(lookback+1):-1], 14)
            rsi2 = calculate_rsi(prices[-lookback:], 14)
            if rsi1 is None or rsi2 is None:
                continue
            # اگر جهت قیمت و بهبود RSI متناقض باشند، واگرایی محتمل است → برگرد False
            price_up = p_slice[-1] > p_slice[0]
            rsi_improve = rsi2 > rsi1
            if (price_up and not rsi_improve) or (not price_up and rsi_improve):
                return False
    return True

# یادداشت: برای دقت بالاتر واگرایی، بهتر است سری کامل MACD/RSI استفاده شود.
