from dataclasses import dataclass
from typing import List

# ✅ ساختار نتیجه هر قانون
@dataclass
class RuleResult:
    name: str       # نام قانون
    passed: bool    # آیا قانون پاس شد یا نه
    detail: str     # توضیح یا دلیل پاس/رد

    def __str__(self):
        status = "✅" if self.passed else "❌"
        return f"{status} {self.name}: {self.detail}"


# 📊 تابع کمکی برای محاسبه قدرت کندل
def body_strength(open_price: float, close_price: float, high: float, low: float) -> float:
    """
    محاسبه قدرت کندل بر اساس نسبت بدنه به کل محدوده کندل.
    خروجی بین 0 و 1 خواهد بود.
    """
    body = abs(close_price - open_price)
    range_ = max(high - low, 1e-6)  # جلوگیری از تقسیم بر صفر
    return body / range_
from typing import List
from config import RISK_LEVELS

# 📊 قانون قدرت کندل 15m
def rule_body_strength(open_15m: float, close_15m: float, high_15m: float, low_15m: float, risk_rules: dict) -> RuleResult:
    bs = abs(close_15m - open_15m) / max(high_15m - low_15m, 1e-6)
    th = risk_rules.get("candle_15m_strength", 0.5)
    ok = bs >= th
    return RuleResult("قدرت کندل 15m", ok, f"BS15={bs:.3f} [حد ≥ {th}]")

# 📊 قانون قدرت کندل 5m
def rule_body_strength_5m(open_5m: float, close_5m: float, high_5m: float, low_5m: float, risk_rules: dict) -> RuleResult:
    bs = abs(close_5m - open_5m) / max(high_5m - low_5m, 1e-6)
    th = risk_rules.get("candle_5m_strength", 0.5)
    ok = bs >= th
    return RuleResult("قدرت کندل 5m", ok, f"BS5={bs:.3f} [حد ≥ {th}]")

# 📊 قانون روند EMA در تایم‌فریم 4h
def rule_trend_4h(ema21_4h: float, ema55_4h: float, ema200_4h: float, direction: str, risk_rules: dict) -> RuleResult:
    emas = risk_rules.get("trend_4h_emas", [21, 55])
    ok = False
    if direction == "LONG":
        ok = ema21_4h > ema55_4h and (200 not in emas or ema55_4h > ema200_4h)
    else:
        ok = ema21_4h < ema55_4h and (200 not in emas or ema55_4h < ema200_4h)
    return RuleResult("روند EMA 4h", ok, f"EMA21={ema21_4h:.2f}, EMA55={ema55_4h:.2f}, EMA200={ema200_4h:.2f}")

# 📊 قانون روند EMA در تایم‌فریم 1h
def rule_trend_1h(ema21_1h: float, ema55_1h: float, direction: str, risk_rules: dict) -> RuleResult:
    emas = risk_rules.get("trend_1h_emas", [21, 55])
    ok = False
    if direction == "LONG":
        ok = ema21_1h > ema55_1h
    else:
        ok = ema21_1h < ema55_1h
    return RuleResult("روند EMA 1h", ok, f"EMA21={ema21_1h:.2f}, EMA55={ema55_1h:.2f}")

# 📊 قانون RSI
def rule_rsi(rsi_30m: float, direction: str, risk_rules: dict) -> RuleResult:
    th_count = risk_rules.get("rsi_threshold_count", 4)
    ok = False
    if direction == "LONG":
        ok = rsi_30m > 50
    else:
        ok = rsi_30m < 50
    return RuleResult("RSI 30m", ok, f"RSI={rsi_30m:.2f} [حد ≥ {th_count}]")

# 📊 قانون MACD
def rule_macd(macd_hist_30m, direction: str, risk_rules: dict) -> RuleResult:
    th_count = risk_rules.get("macd_threshold_count", 4)

    # اگر ورودی لیست بود، آخرین مقدار را بگیر
    if isinstance(macd_hist_30m, list):
        macd_hist_30m = macd_hist_30m[-1] if macd_hist_30m else 0.0

    ok = macd_hist_30m > 0 if direction == "LONG" else macd_hist_30m < 0
    return RuleResult("MACD 30m", ok, f"MACD_hist={macd_hist_30m:.4f} [حد ≥ {th_count}]")


# 📊 قانون شکست ورود
def rule_entry_break(price_30m: float, ema21_30m: float, direction: str, risk_rules: dict) -> RuleResult:
    th = risk_rules.get("entry_break_threshold", 0.0)
    ok = False
    if direction == "LONG":
        ok = price_30m > ema21_30m * (1 + th)
    else:
        ok = price_30m < ema21_30m * (1 - th)
    return RuleResult("شکست ورود", ok, f"Price={price_30m:.2f}, EMA21={ema21_30m:.2f}, Th={th}")
from typing import Tuple

def evaluate_rules(
    symbol: str,
    direction: str,
    risk: str,
    risk_rules: dict,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    ema21_30m: float, ema8_30m: float,
    ema21_1h: float, ema55_1h: float,
    ema21_4h: float, ema55_4h: float, ema200_4h: float = 0.0,
    macd_hist_30m: float = 0.0,
    rsi_30m: float = 50.0,
    vol_spike_factor: float = 1.0,
    divergence_detected: bool = False
) -> Tuple[List[RuleResult], int]:
    """
    اجرای قوانین برای یک نماد با توجه به سطح ریسک.
    خروجی: لیست RuleResult و تعداد قوانین پاس‌شده
    """

    results: List[RuleResult] = []

    # قوانین مختلف
    results.append(rule_body_strength(open_15m, close_15m, high_15m, low_15m, risk_rules))
    results.append(rule_trend_1h(ema21_1h, ema55_1h, direction, risk_rules))
    results.append(rule_trend_4h(ema21_4h, ema55_4h, ema200_4h, direction, risk_rules))
    results.append(rule_rsi(rsi_30m, direction, risk_rules))
    results.append(rule_macd(macd_hist_30m, direction, risk_rules))
    results.append(rule_entry_break(price_30m, ema21_30m, direction, risk_rules))

    # می‌توانی قوانین بیشتری اضافه کنی (مثل کندل 5m یا حجم)
    # results.append(rule_body_strength_5m(...))

    # شمارش قوانین پاس‌شده
    passed_count = sum(1 for r in results if r.passed)

    return results, passed_count
from datetime import datetime
from zoneinfo import ZoneInfo
from signal_store import append_signal_row, tehran_time_str

def generate_signal(
    symbol: str,
    direction: str,
    prefer_risk: str,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    ema21_30m: float, ema55_30m: float, ema8_30m: float,
    ema21_1h: float, ema55_1h: float,
    ema21_4h: float, ema55_4h: float,
    macd_line_5m: float, hist_5m: float,
    macd_line_15m: float, hist_15m: float,
    macd_line_30m: float, hist_30m: float,
    macd_line_1h: float, hist_1h: float,
    macd_line_4h: float, hist_4h: float,
    rsi_5m: float, rsi_15m: float, rsi_30m: float, rsi_1h: float, rsi_4h: float,
    atr_val_30m: float,
    curr_vol: float,
    avg_vol_30m: float,
    divergence_detected: bool
):
    """
    تولید سیگنال نهایی بر اساس نتایج قوانین و سطح ریسک انتخاب‌شده.
    """

    # 🕒 زمان تهران
    tehran_now = datetime.now(ZoneInfo("Asia/Tehran"))
    time_str = tehran_time_str(tehran_now)

    # 📊 ساختار سیگنال
    signal = {
        "symbol": symbol,
        "direction": direction,
        "risk": prefer_risk,
        "price": price_30m,
        "time": time_str,
        "ema21_30m": ema21_30m,
        "ema55_30m": ema55_30m,
        "ema8_30m": ema8_30m,
        "ema21_1h": ema21_1h,
        "ema55_1h": ema55_1h,
        "ema21_4h": ema21_4h,
        "ema55_4h": ema55_4h,
        "macd_hist_30m": hist_30m,
        "rsi_30m": rsi_30m,
        "atr_val_30m": atr_val_30m,
        "curr_vol": curr_vol,
        "avg_vol_30m": avg_vol_30m,
        "divergence": divergence_detected
    }

    # ذخیره سیگنال در فایل/دیتابیس
    append_signal_row(signal)

    return signal
