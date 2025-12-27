# ===== EMA Rejection =====
def ema_rejection(prices, ema_value, tolerance=0.002):
    """
    بررسی می‌کند آیا قیمت به EMA نزدیک شده و رد شده است.
    """
    if not prices or ema_value is None:
        return False
    last_price = prices[-1]
    prev_price = prices[-2] if len(prices) > 1 else None
    if prev_price and abs(prev_price - ema_value) / ema_value <= tolerance:
        return last_price < ema_value
    return False

# ===== Resistance Test =====
def resistance_test(prices, resistance_level, tolerance=0.002):
    """
    بررسی برخورد قیمت به مقاومت و برگشت.
    """
    if not prices or resistance_level is None:
        return False
    last_price = prices[-1]
    prev_price = prices[-2] if len(prices) > 1 else None
    return prev_price and prev_price >= resistance_level and last_price < resistance_level * (1 - tolerance)

# ===== Pullback =====
def pullback(prices, trend_direction='LONG', lookback=5):
    """
    بررسی وجود پولبک در روند اصلی.
    """
    if len(prices) < lookback:
        return False
    recent = prices[-lookback:]
    if trend_direction == 'LONG':
        return recent[-1] < max(recent[:-1])
    else:
        return recent[-1] > min(recent[:-1])

# ===== Double Top/Bottom =====
def double_top_bottom(prices, lookback=10, tolerance=0.003):
    """
    تشخیص الگوی Double Top یا Double Bottom.
    """
    if len(prices) < lookback:
        return None
    recent = prices[-lookback:]
    high_points = sorted(recent)[-2:]
    low_points = sorted(recent)[:2]
    if abs(high_points[0] - high_points[1]) / high_points[0] <= tolerance:
        return "DoubleTop"
    if abs(low_points[0] - low_points[1]) / low_points[0] <= tolerance:
        return "DoubleBottom"
    return None
