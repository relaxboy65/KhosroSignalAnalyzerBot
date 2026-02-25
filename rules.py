import logging
import aiohttp
import asyncio
from dataclasses import dataclass
from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo

from config import (
    RISK_LEVELS, RISK_PARAMS, RISK_FACTORS,
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

# ===== SAFE V3 + لاگ کامل مثل قبل =====
async def generate_signal(
    symbol: str,
    direction: str,
    price_30m: float,
    ema21_1h: float,
    ema50_1h: float,
    ema21_4h: float,
    ema50_4h: float,
    adx: float,
    di_plus: float,
    di_minus: float,
    ema21_30m: float,
    rsi_30m: float,
    candles_30m: list,
    atr_30m: float,
    buffer: float = 0.0012
) -> dict:
    rule_results: List[RuleResult] = []

    # 1️⃣ Mandatory Trend & Range
    if direction == "LONG":
        trend_1h_ok = ema21_1h > ema50_1h and price_30m > ema21_1h * 0.999
        trend_4h_ok = ema21_4h > ema50_4h
        adx_ok = adx > 25 and di_plus > di_minus
    else:
        trend_1h_ok = ema21_1h < ema50_1h and price_30m < ema21_1h * 1.001
        trend_4h_ok = ema21_4h < ema50_4h
        adx_ok = adx > 25 and di_minus > di_plus

    ema_distance = abs(ema21_1h - ema50_1h) / price_30m
    range_ok = ema_distance > 0.0085

    rule_results.append(RuleResult("روند EMA 1h", trend_1h_ok, f"EMA21={ema21_1h:.2f}, EMA50={ema50_1h:.2f}"))
    rule_results.append(RuleResult("روند EMA 4h", trend_4h_ok, f"EMA21={ema21_4h:.2f}, EMA50={ema50_4h:.2f}"))
    rule_results.append(RuleResult("ADX", adx_ok, f"ADX={adx:.2f}, DI+={di_plus:.2f}, DI-={di_minus:.2f}"))
    rule_results.append(RuleResult("فیلتر رنج", range_ok, f"فاصله EMA={ema_distance:.4f} [>0.0085]"))

    mandatory_passed = trend_1h_ok and trend_4h_ok and adx_ok and range_ok

    # 2️⃣ Pullback Entry
    if direction == "LONG":
        pullback_ok = abs(price_30m - ema21_30m) / ema21_30m < 0.0025
        rsi_ok = 52 <= rsi_30m <= 63
    else:
        pullback_ok = abs(price_30m - ema21_30m) / ema21_30m < 0.0025
        rsi_ok = 37 <= rsi_30m <= 48

    last = candles_30m[-1]
    body = abs(last['c'] - last['o'])
    full = last['h'] - last['l']
    candle_strong = body / full >= 0.60

    rule_results.append(RuleResult("ورود هوشمند پولبک", pullback_ok and rsi_ok and candle_strong,
                                   f"قیمت={price_30m:.4f} EMA={ema21_30m:.4f} RSI={rsi_30m:.1f} BS15={body/full:.3f}"))

    entry_ok = pullback_ok and rsi_ok and candle_strong

    if not (mandatory_passed and entry_ok):
        status = "NO_SIGNAL"
        reason = "Mandatory conditions failed" if not mandatory_passed else "Pullback conditions failed"
    else:
        # 3️⃣ Stop & TP
        if direction == "LONG":
            swing_low = min(c['l'] for c in candles_30m[-8:])
            stop_loss = swing_low * (1 - buffer)
        else:
            swing_high = max(c['h'] for c in candles_30m[-8:])
            stop_loss = swing_high * (1 + buffer)

        risk = abs(price_30m - stop_loss)
        take_profit = price_30m + risk * 2.3 if direction == "LONG" else price_30m - risk * 2.3

        status = "SIGNAL"
        reason = "SAFE_PULLBACK_V3"

        signal_dict = {
            "symbol": symbol,
            "direction": direction,
            "risk": "MEDIUM",
            "status": "SIGNAL",
            "strength": 0.75,
            "price": price_30m,
            "stop_loss": round(stop_loss, 6),
            "take_profit": round(take_profit, 6),
            "time": tehran_time_str(),
            "signal_source": "SAFE_PULLBACK_V3",
            "details": [str(r) for r in rule_results]
        }

        append_signal_row(
            symbol=symbol, direction=direction, risk_level_name="MEDIUM",
            entry_price=price_30m, stop_loss=stop_loss, take_profit=take_profit,
            issued_at_tehran=signal_dict["time"], signal_source="SAFE_PULLBACK_V3",
            position_size_usd=10.0
        )

        msg = f"🟢 SAFE V3\n{symbol} {direction}\nورود: {price_30m:.4f}\nاستاپ: {stop_loss:.4f}\nتارگت: {take_profit:.4f}\nRR: 2.3"
        await send_to_telegram(msg)

        # ====================== لاگ کامل مثل قبل ======================
        passed_list = [str(r) for r in rule_results if r.passed]
        failed_list = [str(r) for r in rule_results if not r.passed]

        logger.info("=" * 80)
        logger.info(f"📊 سیگنال {symbol} | جهت={direction} | ریسک=MEDIUM")
        logger.info(f"📈 قوانین پاس‌شده: وزن=0.75")
        logger.info(f"📊 تعداد قوانین: پاس={len(passed_list)}, رد={len(failed_list)}, کل={len(rule_results)}")
        logger.info("📋 همه قوانین بررسی‌شده:")
        logger.info("\n".join([str(r) for r in rule_results]))
        logger.info("—" * 60)
        logger.info("✅ قوانین پاس‌شده:")
        logger.info("\n".join(passed_list) if passed_list else "هیچ‌کدام")
        logger.info("❌ قوانین ردشده:")
        logger.info("\n".join(failed_list) if failed_list else "هیچ‌کدام")
        logger.info(f"✅ وضعیت نهایی: SIGNAL")
        logger.info(f"🎯 استاپ: {stop_loss:.4f} | تارگت: {take_profit:.4f}")
        logger.info("=" * 80)

        return signal_dict

    # NO_SIGNAL
    passed_list = [str(r) for r in rule_results if r.passed]
    failed_list = [str(r) for r in rule_results if not r.passed]

    logger.info("=" * 80)
    logger.info(f"📊 سیگنال {symbol} | جهت={direction} | ریسک=MEDIUM")
    logger.info(f"📈 قوانین پاس‌شده: وزن=0")
    logger.info(f"📊 تعداد قوانین: پاس={len(passed_list)}, رد={len(failed_list)}, کل={len(rule_results)}")
    logger.info("📋 همه قوانین بررسی‌شده:")
    logger.info("\n".join([str(r) for r in rule_results]))
    logger.info("—" * 60)
    logger.info("✅ قوانین پاس‌شده:")
    logger.info("\n".join(passed_list) if passed_list else "هیچ‌کدام")
    logger.info("❌ قوانین ردشده:")
    logger.info("\n".join(failed_list) if failed_list else "هیچ‌کدام")
    logger.info(f"✅ وضعیت نهایی: NO_SIGNAL")
    logger.info(f"دلیل: {reason}")
    logger.info("=" * 80)

    return {"status": "NO_SIGNAL", "reason": reason}
