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

# ===== SAFE Trend Pullback Engine V3 (پلن A) =====
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
    """
    SAFE Trend Pullback Engine V3 - نسخه نهایی
    """
    if not candles_30m or len(candles_30m) < 10:
        return {"status": "NO_SIGNAL", "reason": "داده ناکافی"}

    # 1️⃣ Mandatory Trend & Range
    if direction == "LONG":
        trend_1h_ok = ema21_1h > ema50_1h and price_30m > ema21_1h * 0.999
        trend_4h_ok = ema21_4h > ema50_4h
        adx_ok = adx > 25 and di_plus > di_minus
    else:  # SHORT
        trend_1h_ok = ema21_1h < ema50_1h and price_30m < ema21_1h * 1.001
        trend_4h_ok = ema21_4h < ema50_4h
        adx_ok = adx > 25 and di_minus > di_plus

    ema_distance = abs(ema21_1h - ema50_1h) / price_30m
    range_ok = ema_distance > 0.0085

    if not (trend_1h_ok and trend_4h_ok and adx_ok and range_ok):
        return {"status": "NO_SIGNAL", "reason": "Mandatory trend/range failed"}

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

    if not (pullback_ok and rsi_ok and candle_strong):
        return {"status": "NO_SIGNAL", "reason": "Pullback conditions failed"}

    # 3️⃣ Structure-based Stop
    if direction == "LONG":
        swing_low = min(c['l'] for c in candles_30m[-8:])
        stop_loss = swing_low * (1 - buffer)
    else:
        swing_high = max(c['h'] for c in candles_30m[-8:])
        stop_loss = swing_high * (1 + buffer)

    # 4️⃣ RR 1:2.3
    risk = abs(price_30m - stop_loss)
    take_profit = price_30m + risk * 2.3 if direction == "LONG" else price_30m - risk * 2.3

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
        "details": ["Mandatory Trend + Pullback + Structure Stop"]
    }

    # ذخیره و ارسال تلگرام
    append_signal_row(
        symbol=symbol,
        direction=direction,
        risk_level_name="MEDIUM",
        entry_price=price_30m,
        stop_loss=stop_loss,
        take_profit=take_profit,
        issued_at_tehran=signal_dict["time"],
        signal_source="SAFE_PULLBACK_V3",
        position_size_usd=10.0
    )

    msg = f"🟢 SAFE V3\n{symbol} {direction}\nورود: {price_30m:.4f}\nاستاپ: {stop_loss:.4f}\nتارگت: {take_profit:.4f}\nRR: 2.3"
    await send_to_telegram(msg)

    return signal_dict
