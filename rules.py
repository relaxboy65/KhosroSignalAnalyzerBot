import logging
import aiohttp
import asyncio
from dataclasses import dataclass
from typing import List, Tuple, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    RISK_LEVELS, RISK_PARAMS, RISK_FACTORS,
    INDICATOR_THRESHOLDS, ADVANCED_RISK_PARAMS,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
from indicators import calculate_adx, calculate_cci, calculate_sar, calculate_stochastic
from patterns import ema_rejection, resistance_test, pullback, double_top_bottom
from signal_store import append_signal_row, tehran_time_str, compose_signal_source

logger = logging.getLogger(__name__)

# ✅ ساختار نتیجه هر قانون
@dataclass
class RuleResult:
    name: str
    passed: bool
    detail: str

    def __str__(self):
        status = "✅" if self.passed else "❌"
        return f"{status} {self.name}: {self.detail}"

# ========== ارسال پیام به تلگرام ==========
async def send_to_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ تنظیمات تلگرام ناقص است")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}

    logger.info("📤 تلاش برای ارسال پیام تلگرام...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=20) as resp:
                body = await resp.text()
                if resp.status == 200:
                    logger.info("✅ پیام به تلگرام ارسال شد")
                else:
                    logger.warning(f"⚠️ خطا در ارسال تلگرام: {resp.status} | پاسخ: {body}")
        except Exception as e:
            logger.error(f"❌ خطا در ارسال به تلگرام: {e}")

# ===== قوانین پایه =====
def rule_body_strength(open_15m: float, close_15m: float, high_15m: float, low_15m: float, risk_rules: dict) -> RuleResult:
    bs = abs(close_15m - open_15m) / max(high_15m - low_15m, 1e-6)
    th = risk_rules.get("candle_15m_strength", 0.5)
    ok = bs >= th
    return RuleResult("قدرت کندل 15m", ok, f"BS15={bs:.3f} [حد ≥ {th}]")

def rule_body_strength_5m(open_5m: float, close_5m: float, high_5m: float, low_5m: float, risk_rules: dict) -> RuleResult:
    bs = abs(close_5m - open_5m) / max(high_5m - low_5m, 1e-6)
    th = risk_rules.get("candle_5m_strength", 0.5)
    ok = bs >= th
    return RuleResult("قدرت کندل 5m", ok, f"BS5={bs:.3f} [حد ≥ {th}]")

def rule_trend_1h(ema21_1h: float, ema55_1h: float, direction: str, risk_rules: dict) -> RuleResult:
    if ema21_1h is None or ema55_1h is None:
        return RuleResult("روند EMA 1h", False, "داده EMA 1h موجود نیست")
    ok = (ema21_1h > ema55_1h) if direction == "LONG" else (ema21_1h < ema55_1h)
    return RuleResult("روند EMA 1h", ok, f"EMA21={ema21_1h:.2f}, EMA55={ema55_1h:.2f}")

def rule_trend_4h(ema21_4h: float, ema55_4h: float, ema200_4h: float, direction: str, risk_rules: dict) -> RuleResult:
    if ema21_4h is None or ema55_4h is None:
        return RuleResult("روند EMA 4h", False, "داده EMA 4h موجود نیست")
    if ema200_4h is None:
        ema200_4h = 0.0
    ok = (ema21_4h > ema55_4h and ema55_4h > ema200_4h) if direction == "LONG" else (ema21_4h < ema55_4h and ema55_4h < ema200_4h)
    return RuleResult("روند EMA 4h", ok, f"EMA21={ema21_4h:.2f}, EMA55={ema55_4h:.2f}, EMA200={ema200_4h:.2f}")

def rule_rsi(rsi_30m: float, direction: str, risk_rules: dict, risk_level: str) -> RuleResult:
    # آستانه‌ها بر اساس سطح ریسک
    if risk_level == "LOW":
        ok = (rsi_30m > 55) if direction == "LONG" else (rsi_30m < 45)
    elif risk_level == "MEDIUM":
        ok = (rsi_30m > 50) if direction == "LONG" else (rsi_30m < 50)
    else:  # HIGH
        ok = (rsi_30m > 45) if direction == "LONG" else (rsi_30m < 55)

    return RuleResult("RSI 30m", ok, f"RSI={rsi_30m:.2f} | سطح={risk_level}")


def rule_macd(macd_hist_30m, direction: str, risk_rules: dict, risk_level: str) -> RuleResult:
    if isinstance(macd_hist_30m, list):
        macd_hist_30m = macd_hist_30m[-1] if macd_hist_30m else 0.0

    if risk_level == "LOW":
        ok = (macd_hist_30m > 0.002) if direction == "LONG" else (macd_hist_30m < -0.002)
    elif risk_level == "MEDIUM":
        ok = (macd_hist_30m > 0) if direction == "LONG" else (macd_hist_30m < 0)
    else:  # HIGH
        ok = (macd_hist_30m >= -0.001) if direction == "LONG" else (macd_hist_30m <= 0.001)

    return RuleResult("MACD 30m", ok, f"MACD_hist={macd_hist_30m:.4f} | سطح={risk_level}")


def rule_entry_break(price_30m: float, ema21_30m: float, direction: str, risk_rules: dict, risk_level: str) -> RuleResult:
    if risk_level == "LOW":
        th = 0.0
    elif risk_level == "MEDIUM":
        th = 0.003
    else:  # HIGH
        th = 0.005   # انعطاف بیشتر برای ورود

    ok = price_30m > ema21_30m * (1 + th) if direction == "LONG" else price_30m < ema21_30m * (1 - th)
    return RuleResult("شکست ورود", ok, f"Price={price_30m:.2f}, EMA21={ema21_30m:.2f}, Th={th} | سطح={risk_level}")


# ===== قوانین جدید =====
def rule_adx(candles: List[dict], risk_rules: dict, risk_level: str) -> RuleResult:
    adx_val = calculate_adx(candles)
    if adx_val is None:
        return RuleResult("ADX", False, "داده کافی نیست")

    if risk_level == "LOW":
        th = INDICATOR_THRESHOLDS["ADX_STRONG"]
    elif risk_level == "MEDIUM":
        th = INDICATOR_THRESHOLDS["ADX_MEDIUM"]
    else:  # HIGH
        th = INDICATOR_THRESHOLDS["ADX_WEAK"]

    ok = adx_val >= th
    return RuleResult("ADX", ok, f"ADX={adx_val:.2f} [حد ≥ {th}] | سطح={risk_level}")

def rule_cci(candles: List[dict], risk_rules: dict, risk_level: str) -> RuleResult:
    cci_val = calculate_cci(candles)
    th_over = INDICATOR_THRESHOLDS["CCI_OVERBOUGHT"]
    th_under = INDICATOR_THRESHOLDS["CCI_OVERSOLD"]
    weight = RISK_FACTORS[risk_level]["CCI"]
    ok = (cci_val is not None and ((cci_val > th_over) or (cci_val < th_under))) if weight >= 3 else (cci_val is not None and abs(cci_val) > 50)
    return RuleResult("CCI", ok, f"CCI={cci_val} [±{th_under}/{th_over}] (وزن={weight})")

def rule_sar(candles: List[dict], direction: str, risk_rules: dict, risk_level: str) -> RuleResult:
    sar_val = calculate_sar(candles)
    last_close = candles[-1]['c']
    ok = (sar_val is not None and sar_val < last_close) if direction == "LONG" else (sar_val is not None and sar_val > last_close)
    return RuleResult("SAR", ok, f"SAR={sar_val}, Close={last_close}, Dir={direction}")

def rule_stochastic(candles: List[dict], direction: str, risk_rules: dict, risk_level: str) -> RuleResult:
    k, d = calculate_stochastic(candles)
    th_over = INDICATOR_THRESHOLDS["STOCH_OVERBOUGHT"]
    th_under = INDICATOR_THRESHOLDS["STOCH_OVERSOLD"]
    weight = RISK_FACTORS[risk_level]["Stoch"]
    if k is None or d is None:
        return RuleResult("Stochastic", False, "K/D=None")
    ok = ((k < th_under and d < th_under) or (weight <= 2 and k > d)) if direction == "LONG" else ((k > th_over and d > th_over) or (weight <= 2 and k < d))
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

# ===== اجرای همه قوانین =====
def evaluate_rules(
    symbol: str,
    direction: str,
    risk: str,
    risk_rules: dict,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    ema21_30m: float, ema8_30m: float,
    ema21_1h: float, ema55_1h: float,
    ema21_4h: float, ema55_4h: float, ema200_4h: float = 0.0,   # 👈 اضافه شد
    macd_hist_30m: float = 0.0,
    rsi_30m: float = 50.0,
    vol_spike_factor: float = 1.0,
    divergence_detected: bool = False,
    candles: Optional[List[dict]] = None,
    closes_by_tf: Optional[dict] = None,
    prices_series_30m: Optional[List[float]] = None
) -> Tuple[List[RuleResult], int]:

    results: List[RuleResult] = []

    # قوانین پایه
    results.append(rule_body_strength(open_15m, close_15m, high_15m, low_15m, risk_rules))
    results.append(rule_body_strength_5m(open_15m, close_15m, high_15m, low_15m, risk_rules))
    results.append(rule_trend_1h(ema21_1h, ema55_1h, direction, risk_rules))
    results.append(rule_trend_4h(ema21_4h, ema55_4h, ema200_4h, direction, risk_rules))  # 👈 حالا ema200_4h پاس داده می‌شود
    results.append(rule_rsi(rsi_30m, direction, risk_rules, risk))
    results.append(rule_macd(macd_hist_30m, direction, risk_rules, risk))
    results.append(rule_entry_break(price_30m, ema21_30m, direction, risk_rules, risk))

    # الگوها
    if prices_series_30m and len(prices_series_30m) >= 10:
        results.append(rule_ema_rejection(prices_series_30m, ema21_30m))
        results.append(rule_pullback(prices_series_30m, direction))
    else:
        results.append(RuleResult("EMA Rejection", False, "سری قیمت کافی نیست"))
        results.append(RuleResult("Pullback", False, "سری قیمت کافی نیست"))

    # قوانین اندیکاتوری جدید
    if candles and isinstance(candles, list) and len(candles) >= 20:
        results.append(rule_adx(candles, risk_rules, risk))       # 👈 اصلاح شد
        results.append(rule_cci(candles, risk_rules, risk))       # 👈 اصلاح شد
        results.append(rule_sar(candles, direction, risk_rules, risk))  # 👈 اصلاح شد
        results.append(rule_stochastic(candles, direction, risk_rules, risk))  # 👈 اصلاح شد
    else:
        results.append(RuleResult("ADX", False, "داده کافی نیست"))
        results.append(RuleResult("CCI", False, "داده کافی نیست"))
        results.append(RuleResult("SAR", False, "داده کافی نیست"))
        results.append(RuleResult("Stochastic", False, "داده کافی نیست"))

    passed_count = sum(1 for r in results if r.passed)
    return results, passed_count


# ===== تولید سیگنال =====
async def generate_signal(
    symbol: str,
    direction: str,
    prefer_risk: str,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    ema21_30m: float, ema55_30m: float, ema8_30m: float,
    ema21_1h: float, ema55_1h: float,
    ema21_4h: float, ema55_4h: float, ema200_4h: float = 0.0,   # 👈 اضافه شد
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
    candles: Optional[List[dict]] = None,
    prices_series_30m: Optional[List[float]] = None
):
    tehran_now = datetime.now(ZoneInfo("Asia/Tehran"))
    time_str = tehran_time_str(tehran_now)

    # محاسبه SL/TP اولیه
    atr_mult = RISK_PARAMS.get("atr_multiplier", 1.2)
    rr_target = RISK_PARAMS.get("rr_target", 2.0)

    if direction == "LONG":
        stop_loss = price_30m - atr_val_30m * atr_mult
        take_profit = price_30m + (price_30m - stop_loss) * rr_target
    else:
        stop_loss = price_30m + atr_val_30m * atr_mult
        take_profit = price_30m - (stop_loss - price_30m) * rr_target

    if isinstance(hist_30m, list):
        hist_30m = hist_30m[-1] if hist_30m else 0.0

    # اجرای قوانین
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
        ema21_4h=ema21_4h, ema55_4h=ema55_4h, ema200_4h=ema200_4h,
        macd_hist_30m=hist_30m,
        rsi_30m=rsi_30m,
        vol_spike_factor=1.0,
        divergence_detected=divergence_detected,
        candles=candles,
        closes_by_tf=None,
        prices_series_30m=prices_series_30m
    )

    adv = ADVANCED_RISK_PARAMS.get(prefer_risk, ADVANCED_RISK_PARAMS["MEDIUM"])
    stop_factor = adv["stop_loss_factor"]
    tp_factor = adv["take_profit_factor"]
    signal_strength = adv["signal_strength"]

    if direction == "LONG":
        stop_loss = price_30m - atr_val_30m * atr_mult * stop_factor
        take_profit = price_30m + (price_30m - stop_loss) * rr_target * tp_factor
    else:
        stop_loss = price_30m + atr_val_30m * atr_mult * stop_factor
        take_profit = price_30m - (stop_loss - price_30m) * rr_target * tp_factor

    min_pass = max(4, len(rule_results) // 2)
    status = "SIGNAL" if passed_count >= min_pass else "NO_SIGNAL"

    # 📊 لاگ کامل
    passed_list = [str(r) for r in rule_results if r.passed]
    failed_list = [str(r) for r in rule_results if not r.passed]

    logger.info("=" * 80)
    logger.info(f"📊 سیگنال {symbol} | جهت={direction} | ریسک={prefer_risk}")
    logger.info(f"📈 قوانین پاس‌شده: {passed_count}/{len(rule_results)}")
    for r in rule_results:
        logger.info(str(r))
    logger.info("—" * 60)
    logger.info("✅ قوانین پاس‌شده:")
    logger.info("\n".join(passed_list) if passed_list else "هیچ‌کدام")
    logger.info("❌ قوانین ردشده:")
    logger.info("\n".join(failed_list) if failed_list else "هیچ‌کدام")
    logger.info(f"✅ وضعیت نهایی: {status}")
    logger.info(f"🎯 استاپ: {stop_loss:.4f} | تارگت: {take_profit:.4f}")
    logger.info("=" * 80)

    # ساخت متن کامل برای ستون signal_source
    rules_passed = [r.name for r in rule_results if r.passed]
    passed_str = ";".join(rules_passed) if rules_passed else ""
    reasons_str = "|".join([r.detail for r in rule_results]) if rule_results else ""

    details_source = (
        f"Dir={direction}"
        f" | TF_EMA=30m:EMA21={ema21_30m:.6f},30m:EMA55={ema55_30m:.6f},"
        f"1h:EMA21={ema21_1h if ema21_1h else 'NA'},1h:EMA55={ema55_1h if ema55_1h else 'NA'},"
        f"4h:EMA21={ema21_4h if ema21_4h else 'NA'},4h:EMA55={ema55_4h if ema55_4h else 'NA'}"
        f" | TF_RSI=30m:RSI={rsi_30m:.2f}"
        f" | TF_MACD=30m:MACD={macd_line_30m if macd_line_30m else 'NA'},30m:HIST={hist_30m if hist_30m else 'NA'}"
        f" | BS15={abs(close_15m-open_15m)/max(high_15m-low_15m,1e-6):.3f}"
        f" | RulesPassed={passed_str}"
        f" | Reasons={reasons_str}"
    )

    # ذخیره در CSV
    append_signal_row(
        symbol=symbol,
        direction=direction,
        risk_level_name=prefer_risk,
        entry_price=price_30m,
        stop_loss=stop_loss,
        take_profit=take_profit,
        issued_at_tehran=time_str,
        signal_source=details_source,
        position_size_usd=10.0
    )

    # ارسال تلگرام با دلایل (فقط وقتی سیگنال معتبر باشد)
    # آیکون جهت معامله
    dir_icon = "🟢" if direction == "LONG" else "🔴"
    
    # مدل ریسک مفهومی‌تر
    risk_icon_map = {
        "LOW": "🛡️ محافظه‌کار",
        "MEDIUM": "⚖️ متعادل",
        "HIGH": "🔥 تهاجمی"
    }
    risk_label = risk_icon_map.get(prefer_risk, "⚖️ متعادل")
    
    # ساخت پیام تلگرام
    msg = (
        f"──────────────\n"
        f"📊 سیگنال {symbol}\n"
        f"جهت: {dir_icon} {direction}\n"
        f"ریسک: {risk_label}\n"
        f"ورود: {price_30m:.4f}\n"
        f"استاپ: {stop_loss:.4f}\n"
        f"تارگت: {take_profit:.4f}\n"
        f"زمان: {time_str}\n"
        f"──────────────\n"
        f"📋 قوانین پاس‌شده ({passed_count}/{len(rule_results)}):\n"
        + "\n".join([f"✅ {r.name} → {r.detail}" for r in rule_results if r.passed]) + "\n"
        f"❌ قوانین ردشده:\n"
        + "\n".join([f"❌ {r.name} → {r.detail}" for r in rule_results if not r.passed])
    )

    await send_to_telegram(msg)   # 👈 اینجا باید هم‌سطح باشه


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
        "signal_source": details_source,   # 👈 اینجا باید details_source باشد
        "details": [str(r) for r in rule_results],
        "passed_count": passed_count,
        "total_rules": len(rule_results)
    }

