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
from indicators import (
    calculate_adx, calculate_cci, calculate_sar, 
    calculate_stochastic, calculate_ema, 
    calculate_swing_low, calculate_swing_high
)
from patterns import ema_rejection, resistance_test, pullback, double_top_bottom
from signal_store import append_signal_row, tehran_time_str

logger = logging.getLogger(__name__)

@dataclass
class RuleResult:
    name: str
    passed: bool
    detail: str

    def __str__(self):
        status = "✅" if self.passed else "❌"
        return f"{status} {self.name}: {self.detail}"

# ========== ارسال تلگرام ==========
async def send_to_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ تنظیمات تلگرام ناقص است")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=20) as resp:
                if resp.status == 200:
                    logger.info("✅ پیام به تلگرام ارسال شد")
                else:
                    logger.warning(f"⚠️ خطا در ارسال تلگرام: {resp.status}")
        except Exception as e:
            logger.error(f"❌ خطا در ارسال به تلگرام: {e}")

# ===== قوانین پایه =====
def rule_body_strength(open_15m, close_15m, high_15m, low_15m, risk_rules) -> RuleResult:
    bs = abs(close_15m - open_15m) / max(high_15m - low_15m, 1e-6)
    th = risk_rules.get("candle_15m_strength", 0.5)
    ok = bs >= th
    return RuleResult("قدرت کندل 15m", ok, f"BS15={bs:.3f} [≥ {th}]")

def rule_body_strength_5m(open_5m, close_5m, high_5m, low_5m, risk_rules) -> RuleResult:
    bs = abs(close_5m - open_5m) / max(high_5m - low_5m, 1e-6)
    th = risk_rules.get("candle_5m_strength", 0.5)
    ok = bs >= th
    return RuleResult("قدرت کندل 5m", ok, f"BS5={bs:.3f} [≥ {th}]")

def rule_trend_1h(ema21_1h, ema50_1h, direction) -> RuleResult:
    if ema21_1h is None or ema50_1h is None:
        return RuleResult("روند EMA 1h", False, "داده موجود نیست")
    ok = (ema21_1h > ema50_1h) if direction == "LONG" else (ema21_1h < ema50_1h)
    return RuleResult("روند EMA 1h", ok, f"EMA21={ema21_1h:.2f}, EMA50={ema50_1h:.2f}")

def rule_trend_4h(ema21_4h, ema50_4h, ema200_4h, direction) -> RuleResult:
    if ema21_4h is None or ema50_4h is None:
        return RuleResult("روند EMA 4h", False, "داده موجود نیست")
    ok = (ema21_4h > ema50_4h and ema50_4h > ema200_4h) if direction == "LONG" else (ema21_4h < ema50_4h and ema50_4h < ema200_4h)
    return RuleResult("روند EMA 4h", ok, f"EMA21={ema21_4h:.2f}, EMA50={ema50_4h:.2f}")

def rule_rsi(rsi_30m, direction, risk_level) -> RuleResult:
    if risk_level == "LOW":
        ok = (rsi_30m > 55) if direction == "LONG" else (rsi_30m < 45)
    elif risk_level == "MEDIUM":
        ok = (rsi_30m > 50) if direction == "LONG" else (rsi_30m < 50)
    else:
        ok = (rsi_30m > 45) if direction == "LONG" else (rsi_30m < 55)
    return RuleResult("RSI 30m", ok, f"RSI={rsi_30m:.2f}")

def rule_macd(macd_hist, direction, risk_level) -> RuleResult:
    if isinstance(macd_hist, list):
        macd_hist = macd_hist[-1] if macd_hist else 0.0
    if risk_level == "LOW":
        ok = (macd_hist > 0.002) if direction == "LONG" else (macd_hist < -0.002)
    elif risk_level == "MEDIUM":
        ok = (macd_hist > 0) if direction == "LONG" else (macd_hist < 0)
    else:
        ok = (macd_hist >= -0.001) if direction == "LONG" else (macd_hist <= 0.001)
    return RuleResult("MACD 30m", ok, f"MACD_hist={macd_hist:.4f}")

# ===== قانون ورود جدید (مرحله ۲) =====
def rule_smart_pullback_entry(price_30m, ema21_30m, rsi_30m, open_15m, close_15m, direction) -> RuleResult:
    if direction == "LONG":
        pullback_ok = price_30m < ema21_30m * 0.997          # حداقل ۰.۳٪ پولبک
        rsi_ok = 50 <= rsi_30m <= 60
        candle_strong = (close_15m - open_15m) / (high_15m - low_15m + 1e-8) >= 0.65
        ok = pullback_ok and rsi_ok and candle_strong
        detail = f"قیمت={price_30m:.4f} EMA={ema21_30m:.4f} RSI={rsi_30m:.1f} BS15={candle_strong}"
    else:
        pullback_ok = price_30m > ema21_30m * 1.003
        rsi_ok = 40 <= rsi_30m <= 50
        candle_strong = (open_15m - close_15m) / (high_15m - low_15m + 1e-8) >= 0.65
        ok = pullback_ok and rsi_ok and candle_strong
        detail = f"قیمت={price_30m:.4f} EMA={ema21_30m:.4f} RSI={rsi_30m:.1f} BS15={candle_strong}"
    
    return RuleResult("ورود هوشمند پولبک", ok, detail)

# ===== قوانین مومنتوم جدید (مرحله ۳) =====
def rule_cci_momentum(candles, direction) -> RuleResult:
    cci = calculate_cci(candles)
    if cci is None:
        return RuleResult("CCI مومنتوم", False, "داده موجود نیست")
    ok = (cci > 0) if direction == "LONG" else (cci < 0)
    return RuleResult("CCI عبور از ۰", ok, f"CCI={cci:.2f}")

def rule_stochastic_momentum(candles, direction) -> RuleResult:
    k, d = calculate_stochastic(candles)
    if k is None or d is None:
        return RuleResult("Stochastic کراس", False, "داده موجود نیست")
    if direction == "LONG":
        ok = (k > d) and (k < 60) and (k > 20)   # کراس صعودی زیر ۶۰
    else:
        ok = (k < d) and (k > 40) and (k < 80)   # کراس نزولی بالای ۴۰
    return RuleResult("Stochastic کراس", ok, f"K={k:.2f} D={d:.2f}")

# ===== قوانین پیشرفته =====
def rule_adx(candles: list, direction: str) -> RuleResult:
    adx, di_plus, di_minus = calculate_adx(candles)
    if adx is None:
        return RuleResult("ADX", False, "داده ADX موجود نیست")
    ok = adx > INDICATOR_THRESHOLDS["ADX_STRONG"]
    detail = f"ADX={adx:.2f} [حد > {INDICATOR_THRESHOLDS['ADX_STRONG']}]"
    return RuleResult("ADX", ok, detail)

def rule_cci(candles: list, direction: str) -> RuleResult:
    cci = calculate_cci(candles)
    if cci is None:
        return RuleResult("CCI", False, "داده CCI موجود نیست")
    ok = (cci > INDICATOR_THRESHOLDS["CCI_OVERBOUGHT"]) if direction == "LONG" else (cci < INDICATOR_THRESHOLDS["CCI_OVERSOLD"])
    return RuleResult("CCI", ok, f"CCI={cci:.2f}")

def rule_sar(candles: list, direction: str) -> RuleResult:
    sar = calculate_sar(candles)
    if sar is None:
        return RuleResult("SAR", False, "داده SAR موجود نیست")
    last_close = candles[-1]['c']
    ok = (last_close > sar) if direction == "LONG" else (last_close < sar)
    return RuleResult("SAR", ok, f"SAR={sar:.4f}, قیمت={last_close:.4f}")

def rule_stochastic(candles: list, direction: str) -> RuleResult:
    k, d = calculate_stochastic(candles)
    if k is None:
        return RuleResult("Stochastic", False, "داده Stochastic موجود نیست")
    ok = (k > INDICATOR_THRESHOLDS["STOCH_OVERBOUGHT"] and k > d) if direction == "LONG" else (k < INDICATOR_THRESHOLDS["STOCH_OVERSOLD"] and k < d)
    return RuleResult("Stochastic", ok, f"K={k:.2f}, D={d:.2f}")

# ===== قوانین الگو =====
def rule_ema_rejection(prices_series_30m: list, ema21_30m: float) -> RuleResult:
    rejected = ema_rejection(prices_series_30m, ema21_30m)
    return RuleResult("رد EMA", rejected, "رد EMA تشخیص داده شد" if rejected else "بدون رد")

def rule_resistance_test(prices_series_30m: list, ema50_30m: float) -> RuleResult:
    tested = resistance_test(prices_series_30m, ema50_30m)
    return RuleResult("تست مقاومت", tested, "تست مقاومت تایید شد" if tested else "بدون تست")

def rule_pullback(prices_series_30m: list, direction: str) -> RuleResult:
    pb = pullback(prices_series_30m, direction)
    return RuleResult("پولبک", pb, "پولبک تشخیص داده شد" if pb else "بدون پولبک")

def rule_double_top_bottom(prices_series_30m: list) -> RuleResult:
    pattern = double_top_bottom(prices_series_30m)
    ok = pattern is not None
    return RuleResult("Double Top/Bottom", ok, f"الگو={pattern}" if ok else "بدون الگو")

# ===== فیلتر رنج جدید =====
def rule_range_filter(ema21_30m: float, ema50_30m: float, price_30m: float) -> RuleResult:
    diff = abs(ema21_30m - ema50_30m) / price_30m if price_30m > 0 else 0
    ok = diff > 0.007
    return RuleResult("فیلتر رنج", ok, f"فاصله EMA={diff:.4f} [حد > 0.007]")

# ===== ارزیابی قوانین =====
# نقشه گروه‌بندی قوانین به وزن‌ها
RULE_GROUP_MAP = {
    "قدرت کندل 15m": "Candles",
    "قدرت کندل 5m": "Candles",
    "روند EMA 1h": "EMA",
    "روند EMA 4h": "TF_Big",
    "RSI 30m": "Confirm",
    "MACD 30m": "Confirm",
    "شکست ورود": "Confirm",
    "ADX": "ADX",
    "CCI": "CCI",
    "SAR": "SAR",
    "Stochastic": "Stoch",
    "رد EMA": "Patterns",
    "تست مقاومت": "Patterns",
    "پولبک": "Patterns",
    "Double Top/Bottom": "Patterns",
    "فیلتر رنج": "RiskMgmt",  # جدید
}

def evaluate_rules(
    symbol: str,
    direction: str,
    risk: str,
    risk_rules: dict,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    open_5m: float, close_5m: float, high_5m: float, low_5m: float,
    open_1m: float, close_1m: float, high_1m: float, low_1m: float,
    ema21_30m: float, ema50_30m: float, ema8_30m: float,
    ema21_1h: float, ema50_1h: float,
    ema21_4h: float, ema50_4h: float, ema200_4h: float,
    macd_hist_30m: float,
    rsi_30m: float,
    vol_spike_factor: float,
    divergence_detected: bool,
    candles: list,
    prices_series_30m: list,
    closes_by_tf: dict
) -> Tuple[List[RuleResult], float, float]:
    weights = RISK_FACTORS.get(risk, {})
    rule_results = [
        rule_body_strength(open_15m, close_15m, high_15m, low_15m, risk_rules),
        rule_body_strength_5m(open_5m, close_5m, high_5m, low_5m, risk_rules),
        rule_trend_1h(ema21_1h, ema50_1h, direction, risk_rules),
        rule_trend_4h(ema21_4h, ema50_4h, ema200_4h, direction, risk_rules),
        rule_rsi(rsi_30m, direction, risk_rules, risk),
        rule_macd(macd_hist_30m, direction, risk_rules, risk),
        rule_entry_break(price_30m, ema21_30m, direction, risk_rules, risk),
        rule_adx(candles, direction),
        rule_cci(candles, direction),
        rule_sar(candles, direction),
        rule_stochastic(candles, direction),
        rule_ema_rejection(prices_series_30m, ema21_30m),
        rule_resistance_test(prices_series_30m, ema50_30m),
        rule_pullback(prices_series_30m, direction),
        rule_double_top_bottom(prices_series_30m),
        rule_range_filter(ema21_30m, ema50_30m, price_30m),  # فیلتر جدید
    ]

    # محاسبه وزن با استفاده از map گروهی
    passed_weight = sum(weights.get(RULE_GROUP_MAP.get(r.name, "Other"), 0) for r in rule_results if r.passed)
    total_weight = sum(weights.get(RULE_GROUP_MAP.get(r.name, "Other"), 0) for r in rule_results)

    return rule_results, passed_weight, total_weight

# ===== تولید سیگنال =====
async def generate_signal(
    symbol: str,
    direction: str,
    prefer_risk: str,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    open_5m: float, close_5m: float, high_5m: float, low_5m: float,
    open_1m: float, close_1m: float, high_1m: float, low_1m: float,
    ema21_30m: float, ema50_30m: float, ema8_30m: float,
    ema21_1h: float, ema50_1h: float,
    ema21_4h: float, ema50_4h: float, ema200_4h: float,
    macd_line_30m: float, hist_30m: float,
    rsi_30m: float,
    atr_val_30m: float,
    curr_vol: float,
    avg_vol_30m: float,
    divergence_detected: bool,
    candles: list,
    prices_series_30m: list,
    closes_by_tf: dict
) -> Optional[dict]:
    time_str = tehran_time_str()

    risk_rules = next((r["rules"] for r in RISK_LEVELS if r["key"] == prefer_risk), RISK_LEVELS[1]["rules"])
    rule_results, passed_weight, total_weight = evaluate_rules(
        symbol=symbol,
        direction=direction,
        risk=prefer_risk,
        risk_rules=risk_rules,
        price_30m=price_30m,
        open_15m=open_15m, close_15m=close_15m, high_15m=high_15m, low_15m=low_15m,
        open_5m=open_5m, close_5m=close_5m, high_5m=high_5m, low_5m=low_5m,
        open_1m=open_1m, close_1m=close_1m, high_1m=high_1m, low_1m=low_1m,
        ema21_30m=ema21_30m, ema50_30m=ema50_30m, ema8_30m=ema8_30m,
        ema21_1h=ema21_1h, ema50_1h=ema50_1h,
        ema21_4h=ema21_4h, ema50_4h=ema50_4h, ema200_4h=ema200_4h,
        macd_hist_30m=hist_30m,
        rsi_30m=rsi_30m,
        vol_spike_factor=1.0,
        divergence_detected=divergence_detected,
        candles=candles,
        prices_series_30m=prices_series_30m,
        closes_by_tf=closes_by_tf
    )

    # مدیریت ریسک پویا
    strength_ratio = passed_weight / total_weight if total_weight > 0 else 0
    if strength_ratio >= 0.7:
        atr_mult, rr_target = 1.0, 2.5
    elif strength_ratio >= 0.5:
        atr_mult, rr_target = 1.2, 2.0
    else:
        atr_mult, rr_target = 1.5, 1.5

    # محاسبه استاپ و تارگت - جدید: استاپ ساختارمحور
    if direction == "LONG":
        swing_low = calculate_swing_low(candles)
        buffer = 0.001 * price_30m  # buffer کوچک
        stop_loss = swing_low - buffer
        take_profit = price_30m + (price_30m - stop_loss) * rr_target
    else:
        swing_high = calculate_swing_high(candles)  # فرض بر وجود تابع calculate_swing_high
        buffer = 0.001 * price_30m
        stop_loss = swing_high + buffer
        take_profit = price_30m - (stop_loss - price_30m) * rr_target

    # دسته‌بندی ریسک نهایی
    core_rules = ["روند EMA 1h", "روند EMA 4h", "ADX", "RSI 30m"]
    core_passed = all(any(r.name == cr and r.passed for r in rule_results) for cr in core_rules)
    if core_passed:
        final_risk = "LOW"
    elif passed_weight >= total_weight * 0.5:
        final_risk = "MEDIUM"
    else:
        final_risk = "HIGH"

    status = "SIGNAL" if passed_weight >= total_weight * 0.6 else "NO_SIGNAL"

    # 📊 لاگ کامل
    passed_list = [str(r) for r in rule_results if r.passed]
    failed_list = [str(r) for r in rule_results if not r.passed]
    total_rules = len(rule_results)
    passed_rules_count = len(passed_list)
    failed_rules_count = len(failed_list)

    logger.info("=" * 80)
    logger.info(f"📊 سیگنال {symbol} | جهت={direction} | ریسک={final_risk}")
    logger.info(f"📈 قوانین پاس‌شده: وزن={passed_weight}/{total_weight}")
    logger.info(f"📊 تعداد قوانین: پاس={passed_rules_count}, رد={failed_rules_count}, کل={total_rules}")
    logger.info("📋 همه قوانین بررسی‌شده:")
    logger.info("\n".join([str(r) for r in rule_results]))
    logger.info("—" * 60)
    logger.info("✅ قوانین پاس‌شده:")
    logger.info("\n".join(passed_list) if passed_list else "هیچ‌کدام")
    logger.info("❌ قوانین ردشده:")
    logger.info("\n".join(failed_list) if failed_list else "هیچ‌کدام")
    logger.info(f"✅ وضعیت نهایی: {status}")
    logger.info(f"🎯 استاپ: {stop_loss:.4f} | تارگت: {take_profit:.4f}")
    logger.info("=" * 80)

    signal_dict = {
"symbol": symbol,
        "direction": direction,
        "risk": final_risk,
        "status": status,
        "strength": passed_weight / total_weight if status == "SIGNAL" else None,
        "price": price_30m,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "time": time_str,
        "signal_source": ";".join([str(r) for r in rule_results]),
        "details": [str(r) for r in rule_results],
        "passed_weight": passed_weight,
        "total_weight": total_weight
    }

    # فقط اگر status == "SIGNAL" باشد، ذخیره و ارسال کن
    if status == "SIGNAL":
        # ذخیره در CSV
        append_signal_row(
            symbol=symbol,
            direction=direction,
            risk_level_name=final_risk,
            entry_price=price_30m,
            stop_loss=stop_loss,
            take_profit=take_profit,
            issued_at_tehran=time_str,
            signal_source=";".join([str(r) for r in rule_results]),
            position_size_usd=10.0
        )

        # ارسال تلگرام
        dir_icon = "🟢" if direction == "LONG" else "🔴"
        risk_icon_map = {
            "LOW": "🛡️ محافظه‌کار",
            "MEDIUM": "⚖️ متعادل",
            "HIGH": "🔥 تهاجمی"
        }
        risk_label = risk_icon_map.get(final_risk, "⚖️ متعادل")

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
            f"📋 قوانین پاس‌شده: وزن={passed_weight}/{total_weight} | تعداد={passed_rules_count}/{total_rules}\n"
            + "\n".join([f"✅ {r.name} → {r.detail}" for r in rule_results if r.passed]) + "\n"
            f"❌ قوانین ردشده ({failed_rules_count}):\n"
            + "\n".join([f"❌ {r.name} → {r.detail}" for r in rule_results if not r.passed])
        )
        await send_to_telegram(msg)

    return signal_dict
