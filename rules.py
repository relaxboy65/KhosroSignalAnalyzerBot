import logging
from bot import send_to_telegram   # توجه: اگر تابع در bot.py هست، ایمپورت کن
from dataclasses import dataclass
from typing import List, Tuple, Optional
from config import RISK_LEVELS, RISK_PARAMS, RISK_FACTORS, INDICATOR_THRESHOLDS, ADVANCED_RISK_PARAMS
from indicators import calculate_adx, calculate_cci, calculate_sar, calculate_stochastic
from patterns import  ema_rejection, resistance_test, pullback, double_top_bottom
from signal_store import append_signal_row, tehran_time_str, compose_signal_source
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

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

# 📊 قانون روند EMA در تایم‌فریم 1h
def rule_trend_1h(ema21_1h: float, ema55_1h: float, direction: str, risk_rules: dict) -> RuleResult:
    if ema21_1h is None or ema55_1h is None:
        return RuleResult("روند EMA 1h", False, "داده EMA 1h موجود نیست")
    if direction == "LONG":
        ok = ema21_1h > ema55_1h
    else:
        ok = ema21_1h < ema55_1h
    return RuleResult("روند EMA 1h", ok, f"EMA21={ema21_1h:.2f}, EMA55={ema55_1h:.2f}")

# 📊 قانون روند EMA در تایم‌فریم 4h
def rule_trend_4h(ema21_4h: float, ema55_4h: float, ema200_4h: float, direction: str, risk_rules: dict) -> RuleResult:
    if ema21_4h is None or ema55_4h is None:
        return RuleResult("روند EMA 4h", False, "داده EMA 4h موجود نیست")
    if ema200_4h is None:
        ema200_4h = 0.0  # اگر داده EMA200 نبود، مقدار پیش‌فرض

    if direction == "LONG":
        ok = ema21_4h > ema55_4h and ema55_4h > ema200_4h
    else:
        ok = ema21_4h < ema55_4h and ema55_4h < ema200_4h
    return RuleResult("روند EMA 4h", ok, f"EMA21={ema21_4h:.2f}, EMA55={ema55_4h:.2f}, EMA200={ema200_4h:.2f}")

# 📊 قانون RSI (30m)
def rule_rsi(rsi_30m: float, direction: str, risk_rules: dict) -> RuleResult:
    th_count = risk_rules.get("rsi_threshold_count", 4)
    ok = (rsi_30m > 50) if direction == "LONG" else (rsi_30m < 50)
    return RuleResult("RSI 30m", ok, f"RSI={rsi_30m:.2f} [حد ≥ {th_count}]")

# 📊 قانون MACD (30m)
def rule_macd(macd_hist_30m, direction: str, risk_rules: dict) -> RuleResult:
    th_count = risk_rules.get("macd_threshold_count", 4)
    if isinstance(macd_hist_30m, list):
        macd_hist_30m = macd_hist_30m[-1] if macd_hist_30m else 0.0
    ok = macd_hist_30m > 0 if direction == "LONG" else macd_hist_30m < 0
    return RuleResult("MACD 30m", ok, f"MACD_hist={macd_hist_30m:.4f} [حد ≥ {th_count}]")

# 📊 قانون شکست ورود
def rule_entry_break(price_30m: float, ema21_30m: float, direction: str, risk_rules: dict) -> RuleResult:
    th = risk_rules.get("entry_break_threshold", 0.0)
    if direction == "LONG":
        ok = price_30m > ema21_30m * (1 + th)
    else:
        ok = price_30m < ema21_30m * (1 - th)
    return RuleResult("شکست ورود", ok, f"Price={price_30m:.2f}, EMA21={ema21_30m:.2f}, Th={th}")
# 📊 قانون ADX
def rule_adx(candles: List[dict], risk_rules: dict, risk_level: str) -> RuleResult:
    adx_val = calculate_adx(candles)
    th_strong = INDICATOR_THRESHOLDS["ADX_STRONG"]
    weight = RISK_FACTORS[risk_level]["ADX"]
    ok = adx_val is not None and adx_val >= th_strong if weight >= 2 else (adx_val is not None and adx_val >= INDICATOR_THRESHOLDS["ADX_WEAK"])
    return RuleResult("ADX", ok, f"ADX={adx_val} [حد {('قوی ' + str(th_strong)) if weight>=2 else ('ضعیف ' + str(INDICATOR_THRESHOLDS['ADX_WEAK']))}]")

# 📊 قانون CCI
def rule_cci(candles: List[dict], risk_rules: dict, risk_level: str) -> RuleResult:
    cci_val = calculate_cci(candles)
    th_over = INDICATOR_THRESHOLDS["CCI_OVERBOUGHT"]
    th_under = INDICATOR_THRESHOLDS["CCI_OVERSOLD"]
    weight = RISK_FACTORS[risk_level]["CCI"]
    ok = cci_val is not None and ((cci_val > th_over) or (cci_val < th_under)) if weight >= 3 else (cci_val is not None and abs(cci_val) > 50)
    return RuleResult("CCI", ok, f"CCI={cci_val} [±{th_under}/{th_over}] (وزن={weight})")

# 📊 قانون SAR (روند صعودی اگر SAR زیر Close باشد)
def rule_sar(candles: List[dict], direction: str, risk_rules: dict, risk_level: str) -> RuleResult:
    sar_val = calculate_sar(candles)
    last_close = candles[-1]['c']
    if direction == "LONG":
        ok = sar_val is not None and sar_val < last_close
    else:
        ok = sar_val is not None and sar_val > last_close
    return RuleResult("SAR", ok, f"SAR={sar_val}, Close={last_close}, Dir={direction}")

# 📊 قانون Stochastic
def rule_stochastic(candles: List[dict], direction: str, risk_rules: dict, risk_level: str) -> RuleResult:
    k, d = calculate_stochastic(candles)
    th_over = INDICATOR_THRESHOLDS["STOCH_OVERBOUGHT"]
    th_under = INDICATOR_THRESHOLDS["STOCH_OVERSOLD"]
    weight = RISK_FACTORS[risk_level]["Stoch"]
    if k is None or d is None:
        return RuleResult("Stochastic", False, "K/D=None")
    if direction == "LONG":
        ok = (k < th_under and d < th_under) or (weight <= 2 and k > d)  # در وزن‌های پایین انعطاف
    else:
        ok = (k > th_over and d > th_over) or (weight <= 2 and k < d)
    return RuleResult("Stochastic", ok, f"K={k}, D={d}, Dir={direction} [±{th_under}/{th_over}] (وزن={weight})")

# ===== الگوهای کلاسیک =====
def rule_ema_rejection(prices: List[float], ema_val: float) -> RuleResult:
    ok = ema_rejection(prices, ema_val)
    return RuleResult("EMA Rejection", ok, f"EMA={ema_val:.4f}, Last={prices[-1]:.4f}")

def rule_resistance(prices: List[float], candles: List[dict]) -> RuleResult:
    resistance_level = max([c['h'] for c in candles[-10:]]) if len(candles) >= 10 else None
    ok = resistance_level is not None and resistance_test(prices, resistance_level)
    return RuleResult("Resistance Test", ok, f"Res={('%.4f' % resistance_level) if resistance_level else 'None'}, Last={prices[-1]:.4f}")

def rule_pullback(prices: List[float], direction="LONG") -> RuleResult:
    ok = pullback(prices, trend_direction=direction)
    return RuleResult("Pullback", ok, f"Last={prices[-1]:.4f}, Dir={direction}")

def rule_double(prices: List[float]) -> RuleResult:
    dbl = double_top_bottom(prices)
    ok = dbl is not None
    return RuleResult("Double Top/Bottom", ok, f"Pattern={dbl if dbl else 'None'}")
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
    divergence_detected: bool = False,
    # ورودی‌های جدید برای قوانین پیشرفته:
    candles: Optional[List[dict]] = None,
    closes_by_tf: Optional[dict] = None,
    prices_series_30m: Optional[List[float]] = None
) -> Tuple[List[RuleResult], int]:
    """
    اجرای قوانین برای یک نماد با توجه به سطح ریسک.
    خروجی: لیست RuleResult و تعداد قوانین پاس‌شده
    """

    results: List[RuleResult] = []

    # قوانین موجود شما
    results.append(rule_body_strength(open_15m, close_15m, high_15m, low_15m, risk_rules))
    results.append(rule_trend_1h(ema21_1h, ema55_1h, direction, risk_rules))
    results.append(rule_trend_4h(ema21_4h, ema55_4h, ema200_4h, direction, risk_rules))
    results.append(rule_rsi(rsi_30m, direction, risk_rules))
    results.append(rule_macd(macd_hist_30m, direction, risk_rules))
    results.append(rule_entry_break(price_30m, ema21_30m, direction, risk_rules))

    # قوانین پیشرفته (اگر داده‌ها موجود باشند)
    if candles and isinstance(candles, list) and len(candles) >= 20:
        results.append(rule_adx(candles, risk_rules, risk))
        results.append(rule_cci(candles, risk_rules, risk))
        results.append(rule_sar(candles, direction, risk_rules, risk))
        results.append(rule_stochastic(candles, direction, risk_rules, risk))

    # الگوهای کلاسیک (اگر سری قیمت موجود باشد)
    if prices_series_30m and len(prices_series_30m) >= 10:
        # برای EMA rejection از EMA21_30m به‌عنوان EMA استفاده می‌کنیم
        results.append(rule_ema_rejection(prices_series_30m, ema21_30m))
        results.append(rule_resistance(prices_series_30m, candles if candles else []))
        results.append(rule_pullback(prices_series_30m, direction))
        results.append(rule_double(prices_series_30m))

    passed_count = sum(1 for r in results if r.passed)
    return results, passed_count
def generate_signal(
    symbol: str,
    direction: str,
    prefer_risk: str,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    ema21_30m: float, ema55_30m: float, ema8_30m: float,
    ema21_1h: float, ema55_1h: float,
    ema21_4h: float, ema55_4h: float,
    macd_line_5m: float, hist_5m,
    macd_line_15m: float, hist_15m,
    macd_line_30m: float, hist_30m,
    macd_line_1h: float, hist_1h,
    macd_line_4h: float, hist_4h,
    rsi_5m: float, rsi_15m: float, rsi_30m: float, rsi_1h: float, rsi_4h: float,
    atr_val_30m: float,
    curr_vol: float,
    avg_vol_30m: float,
    divergence_detected: bool,
    check_result=None,
    analysis_data=None,
    # ورودی‌های تکمیلی برای قوانین پیشرفته:
    candles: Optional[List[dict]] = None,
    prices_series_30m: Optional[List[float]] = None
):
    """
    تولید سیگنال نهایی. نسخه‌ی شما حفظ شده و فقط مدیریت ریسک پیشرفته و دیتیل‌ها اضافه شده‌اند.
    """

    # زمان تهران
    tehran_now = datetime.now(ZoneInfo("Asia/Tehran"))
    time_str = tehran_time_str(tehran_now)

    # محاسبه استاپ و تارگت (بر اساس config.RISK_PARAMS)
    atr_mult = RISK_PARAMS.get("atr_multiplier", 1.2)
    rr_target = RISK_PARAMS.get("rr_target", 2.0)

    if direction == "LONG":
        stop_loss = price_30m - atr_val_30m * atr_mult
        take_profit = price_30m + (price_30m - stop_loss) * rr_target
    else:
        stop_loss = price_30m + atr_val_30m * atr_mult
        take_profit = price_30m - (stop_loss - price_30m) * rr_target

    # MACD هیستوگرام نرمال‌سازی
    if isinstance(hist_30m, list):
        hist_30m = hist_30m[-1] if hist_30m else 0.0

    # ساخت رشته کامل برای CSV
    if check_result and analysis_data:
        signal_source = compose_signal_source(check_result, analysis_data, direction)
    else:
        signal_source = "NA"

    # ارزیابی قوانین با سطح ریسک انتخابی
    risk_rules = next((r["rules"] for r in RISK_LEVELS if r["key"] == prefer_risk), RISK_LEVELS[1]["rules"])
    rule_results, passed_count = evaluate_rules(
        symbol=symbol,
        direction=direction,
        risk=prefer_risk,
        risk_rules=risk_rules,
        price_30m=price_30m,
        open_15m=open_15m, close_15m=close_15m, high_15m=high_15m, low_15m=low_15m,
        ema21_30m=ema21_30m, ema8_30m=ema8_30m,
        ema21_1h=ema21_1h, ema55_1h=ema55_1h,
        ema21_4h=ema21_4h, ema55_4h=ema55_4h, ema200_4h=0.0,
        macd_hist_30m=hist_30m,
        rsi_30m=rsi_30m,
        vol_spike_factor=1.0,
        divergence_detected=divergence_detected,
        candles=candles,
        closes_by_tf=None,
        prices_series_30m=prices_series_30m
    )

    # مدیریت ریسک پیشرفته (قدرت سیگنال از ADVANCED_RISK_PARAMS)
    adv = ADVANCED_RISK_PARAMS.get(prefer_risk, ADVANCED_RISK_PARAMS["MEDIUM"])
    signal_strength = adv["signal_strength"]
    stop_factor = adv["stop_loss_factor"]
    tp_factor = adv["take_profit_factor"]

    # تنظیمات نهایی SL/TP با فاکتور قدرت سیگنال
    if direction == "LONG":
        stop_loss = price_30m - atr_val_30m * atr_mult * stop_factor
        take_profit = price_30m + (price_30m - stop_loss) * rr_target * tp_factor
    else:
        stop_loss = price_30m + atr_val_30m * atr_mult * stop_factor
        take_profit = price_30m - (stop_loss - price_30m) * rr_target * tp_factor

    # شرط صدور سیگنال: حداقل نصف قوانین پاس شوند
    min_pass = max(4, len(rule_results) // 2)
    status = "SIGNAL" if passed_count >= min_pass else "NO_SIGNAL"

        # 📊 لاگ کامل
    logger.info("="*80)
    logger.info(f"📊 سیگنال {symbol} | جهت={direction} | ریسک={prefer_risk}")
    for r in results:
        logger.info(str(r))
    logger.info(f"✅ وضعیت نهایی: {status}")
    logger.info(f"🎯 استاپ: {stop_loss:.4f} | تارگت: {take_profit:.4f}")
    logger.info("="*80)

    # ذخیره در CSV
    append_signal_row(
        symbol=symbol,
        direction=direction,
        risk_level_name=prefer_risk,
        entry_price=price_30m,
        stop_loss=stop_loss,
        take_profit=take_profit,
        issued_at_tehran=time_str,
        signal_source=signal_source,
        position_size_usd=10.0
    )

    # خروجی برای تلگرام/نمایش
    return {
        "symbol": symbol,
        "direction": direction,
        "risk": prefer_risk,
        "status": status,
        "strength": signal_strength if status == "SIGNAL" else None,
        "price": price_30m,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "time": time_str,
        "signal_source": signal_source,
        "details": [str(r) for r in rule_results],
        "passed_count": passed_count,
        "total_rules": len(rule_results)
    }
