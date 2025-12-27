import os
import time
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from config import SYMBOLS, RISK_LEVELS
from indicators import (
    calculate_ema, calculate_macd, calculate_rsi, calculate_atr
)
from rules import generate_signal

# اگر کتابخانه صرافی داری، اینجا ایمپورت کن (مثلاً ccxt یا کلاینت خودت)
# import ccxt

# -------------------------------
# ابزار دریافت داده (نمونه ساده/پلیس‌هولدر)
# -------------------------------

def fetch_candles(symbol: str, timeframe: str, limit: int = 150) -> List[dict]:
    """
    خروجی هر کندل: {'o': open, 'h': high, 'l': low, 'c': close}
    این تابع را با منبع واقعی‌ات جایگزین کن.
    """
    # TODO: جایگزین با API واقعی
    # raise NotImplementedError("fetch_candles must be implemented with your data source.")
    return []

def extract_closes(candles: List[dict]) -> List[float]:
    return [c['c'] for c in candles] if candles else []

def ensure_candles_ok(candles: List[dict], min_len: int = 50) -> bool:
    return isinstance(candles, list) and len(candles) >= min_len

# -------------------------------
# دریافت چند تایم‌فریم برای یک نماد
# -------------------------------

TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d", "1w"]

def fetch_all_timeframes(symbol: str, limits: Optional[Dict[str, int]] = None) -> Dict[str, List[dict]]:
    data = {}
    for tf in TIMEFRAMES:
        lim = limits.get(tf, 200) if limits else 200
        candles = fetch_candles(symbol, tf, lim)
        data[tf] = candles
    return data

def latest_price_from_candles(candles: List[dict]) -> Optional[float]:
    return candles[-1]['c'] if candles else None
# -------------------------------
# محاسبه اندیکاتورهای موردنیاز برای rules.generate_signal
# -------------------------------

def compute_indicators_for_symbol(tf_data: Dict[str, List[dict]]) -> Dict[str, dict]:
    ind = {}

    # 30m
    c30 = tf_data.get("30m", [])
    closes_30 = extract_closes(c30)
    ind["30m"] = {
        "price": latest_price_from_candles(c30),
        "ema21": calculate_ema(closes_30, 21) if closes_30 else None,
        "ema55": calculate_ema(closes_30, 55) if closes_30 else None,
        "ema8":  calculate_ema(closes_30, 8)  if closes_30 else None,
        "macd": calculate_macd(closes_30),
        "rsi":  calculate_rsi(closes_30),
        "atr":  calculate_atr(c30) if c30 else None,
        "prices_series": closes_30[-120:] if closes_30 else []
    }

    # 15m
    c15 = tf_data.get("15m", [])
    ind["15m"] = {
        "open": c15[-1]['o'] if c15 else None,
        "close": c15[-1]['c'] if c15 else None,
        "high": c15[-1]['h'] if c15 else None,
        "low":  c15[-1]['l'] if c15 else None,
    }

    # 5m
    c5 = tf_data.get("5m", [])
    ind["5m"] = {
        "open": c5[-1]['o'] if c5 else None,
        "close": c5[-1]['c'] if c5 else None,
        "high": c5[-1]['h'] if c5 else None,
        "low":  c5[-1]['l'] if c5 else None,
    }

    # 1h
    c1h = tf_data.get("1h", [])
    closes_1h = extract_closes(c1h)
    ind["1h"] = {
        "ema21": calculate_ema(closes_1h, 21) if closes_1h else None,
        "ema55": calculate_ema(closes_1h, 55) if closes_1h else None,
        "rsi":   calculate_rsi(closes_1h),
        "macd":  calculate_macd(closes_1h)
    }

    # 4h
    c4h = tf_data.get("4h", [])
    closes_4h = extract_closes(c4h)
    ind["4h"] = {
        "ema21": calculate_ema(closes_4h, 21) if closes_4h else None,
        "ema55": calculate_ema(closes_4h, 55) if closes_4h else None,
        "ema200": calculate_ema(closes_4h, 200) if closes_4h else None,
        "rsi":    calculate_rsi(closes_4h),
        "macd":   calculate_macd(closes_4h)
    }

    # 1d
    c1d = tf_data.get("1d", [])
    ind["1d"] = {
        "price": latest_price_from_candles(c1d),
        "rsi": calculate_rsi(extract_closes(c1d)) if c1d else None
    }

    # 1w
    c1w = tf_data.get("1w", [])
    ind["1w"] = {
        "price": latest_price_from_candles(c1w),
        "rsi": calculate_rsi(extract_closes(c1w)) if c1w else None
    }

    return ind

def assemble_rule_inputs(symbol: str, direction: str, prefer_risk: str, tf_data: Dict[str, List[dict]], ind: Dict[str, dict]) -> dict:
    """
    آماده‌سازی ورودی‌های تابع generate_signal در rules.py با استفاده از داده‌های تایم‌فریم‌ها.
    """
    # استخراج‌های امن
    safe = lambda d, k, default=None: (d.get(k) if d else default)

    return {
        "symbol": symbol,
        "direction": direction,
        "prefer_risk": prefer_risk,
        "price_30m": safe(ind["30m"], "price"),
        "open_15m": safe(ind["15m"], "open"),
        "close_15m": safe(ind["15m"], "close"),
        "high_15m": safe(ind["15m"], "high"),
        "low_15m": safe(ind["15m"], "low"),
        "ema21_30m": safe(ind["30m"], "ema21"),
        "ema55_30m": safe(ind["30m"], "ema55"),
        "ema8_30m":  safe(ind["30m"], "ema8"),
        "ema21_1h":  safe(ind["1h"], "ema21"),
        "ema55_1h":  safe(ind["1h"], "ema55"),
        "ema21_4h":  safe(ind["4h"], "ema21"),
        "ema55_4h":  safe(ind["4h"], "ema55"),
        "macd_line_5m": safe(ind["5m"], "macd", {}).get("macd"),
        "hist_5m":       safe(ind["5m"], "macd", {}).get("histogram"),
        "macd_line_15m": safe(ind["15m"], "macd", {}).get("macd") if "macd" in ind["15m"] else None,
        "hist_15m":      safe(ind["15m"], "macd", {}).get("histogram") if "macd" in ind["15m"] else None,
        "macd_line_30m": safe(ind["30m"], "macd", {}).get("macd"),
        "hist_30m":      safe(ind["30m"], "macd", {}).get("histogram"),
        "macd_line_1h":  safe(ind["1h"], "macd", {}).get("macd"),
        "hist_1h":       safe(ind["1h"], "macd", {}).get("histogram"),
        "macd_line_4h":  safe(ind["4h"], "macd", {}).get("macd"),
        "hist_4h":       safe(ind["4h"], "macd", {}).get("histogram"),
        "rsi_5m": safe(ind["5m"], "rsi"),
        "rsi_15m": safe(ind["15m"], "rsi"),
        "rsi_30m": safe(ind["30m"], "rsi"),
        "rsi_1h": safe(ind["1h"], "rsi"),
        "rsi_4h": safe(ind["4h"], "rsi"),
        "atr_val_30m": safe(ind["30m"], "atr"),
        "curr_vol": None,            # اگر داده حجم داری، مقدار بده
        "avg_vol_30m": None,         # اگر میانگین حجم داری، مقدار بده
        "divergence_detected": False,# اگر واگرایی تشخیص می‌دهی، مقدار بده
        "check_result": None,        # اگر خروجی چک قبلی داری
        "analysis_data": None,       # اگر تحلیل‌های متنی داری
        "candles": tf_data.get("30m", []),               # برای قوانین پیشرفته
        "prices_series_30m": ind["30m"].get("prices_series", [])
    }
# -------------------------------
# انتخاب جهت سیگنال (ساده/پلیس‌هولدر)
# -------------------------------
def decide_direction(ind: Dict[str, dict]) -> str:
    """
    تصمیم جهت ساده: اگر EMA21_30m بالای EMA55_30m باشد LONG، در غیر اینصورت SHORT.
    """
    e21 = ind["30m"].get("ema21")
    e55 = ind["30m"].get("ema55")
    if e21 is not None and e55 is not None:
        return "LONG" if e21 > e55 else "SHORT"
    return "LONG"

# -------------------------------
# پردازش یک نماد
# -------------------------------
def process_symbol(symbol: str, prefer_risk: str = "MEDIUM") -> Optional[dict]:
    tf_data = fetch_all_timeframes(symbol)
    if not tf_data.get("30m"):
        return None

    ind = compute_indicators_for_symbol(tf_data)
    direction = decide_direction(ind)

    inputs = assemble_rule_inputs(symbol, direction, prefer_risk, tf_data, ind)
    signal = generate_signal(**inputs)  # فراخوانی rules.generate_signal

    return signal

# -------------------------------
# اجرای برای همه نمادها
# -------------------------------
def run_bot(prefer_risk: str = "MEDIUM", sleep_sec: int = 5):
    print(f"Starting bot at {datetime.now(ZoneInfo('Asia/Tehran'))} | Risk={prefer_risk}")
    for sym in SYMBOLS:
        try:
            sig = process_symbol(sym, prefer_risk=prefer_risk)
            if sig and sig.get("status") == "SIGNAL":
                print(f"[SIGNAL] {sym} | {sig['direction']} | Price={sig['price']} | SL={sig['stop_loss']} | TP={sig['take_profit']}")
            else:
                print(f"[NO] {sym}")
        except Exception as e:
            print(f"[ERR] {sym}: {e}")
        time.sleep(sleep_sec)
