# -*- coding: utf-8 -*-

from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timezone, timedelta

# ---------------------------
# ریسک و جهت معامله
# ---------------------------
class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class RiskLevel(Enum):
    LOW = "ریسک کم"
    MEDIUM = "ریسک میانی"
    HIGH = "ریسک بالا"

# ---------------------------
# آستانه‌ها بر اساس سطح ریسک
# یادآوری: سطح بالا آسان‌تر از میانی و کم است
# ---------------------------
RISK_THRESHOLDS = {
    RiskLevel.LOW: {
        "BS_min": 0.20,
        "ema_gap_1h_pct": 0.005,       # 0.5%
        "ema_gap_4h_pct": 0.003,       # 0.3%
        "rsi_long": 55,
        "rsi_short": 45,
        "macd_hist_min": 0.005,
        "atr_stop_mult": 1.2,
        "rr_target_mult": 2.0,
        "volume_spike": 1.3,
        "ema_fast_cross": True,
        "min_rules_pass": 7
    },
    RiskLevel.MEDIUM: {
        "BS_min": 0.15,
        "ema_gap_1h_pct": 0.003,       # 0.3%
        "ema_gap_4h_pct": 0.002,       # 0.2%
        "rsi_long": 53,
        "rsi_short": 47,
        "macd_hist_min": 0.003,
        "atr_stop_mult": 1.1,
        "rr_target_mult": 1.8,
        "volume_spike": 1.2,
        "ema_fast_cross": True,
        "min_rules_pass": 6
    },
    RiskLevel.HIGH: {
        "BS_min": 0.10,
        "ema_gap_1h_pct": 0.001,       # 0.1%
        "ema_gap_4h_pct": 0.001,       # 0.1%
        "rsi_long": 51,
        "rsi_short": 49,
        "macd_hist_min": 0.001,
        "atr_stop_mult": 1.2,          # عمداً نزدیک‌بودن استاپ را اصلاح کردیم تا استاپ‌های لحظه‌ای کم شود
        "rr_target_mult": 1.5,
        "volume_spike": 1.1,
        "ema_fast_cross": False,       # در سطح بالا الزام به کراس سریع نداریم
        "min_rules_pass": 5
    }
}

# ---------------------------
# ساختار داده خروجی سیگنال
# ---------------------------
@dataclass
class Signal:
    symbol: str
    direction: Direction
    risk_level: RiskLevel
    entry_price: float
    stop_loss: float
    take_profit: float
    issued_at_tehran: str
    status: str
    hit_time_tehran: Optional[str]
    hit_price: Optional[float]
    broker_fee: float
    final_pnl_usd: float
    position_size_usd: float
    return_pct: float
    signal_source: str
# ---------------------------
# محاسبه اندیکاتورها
# ---------------------------
def ema(values: List[float], period: int) -> List[float]:
    if not values or period <= 1:
        return [values[-1]] if values else []
    k = 2 / (period + 1)
    out = []
    ema_prev = sum(values[:period]) / period
    out = [None] * (period - 1)
    out.append(ema_prev)
    for v in values[period:]:
        ema_prev = v * k + ema_prev * (1 - k)
        out.append(ema_prev)
    return out

def macd(values: List[float], fast: int = 12, slow: int = 26, signal_p: int = 9) -> Tuple[List[float], List[float], List[float]]:
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    # هم‌ترازی طول‌ها
    min_len = min(len(ema_fast), len(ema_slow))
    ema_fast = ema_fast[-min_len:]
    ema_slow = ema_slow[-min_len:]
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal_p)
    min_len2 = min(len(macd_line), len(signal_line))
    macd_line = macd_line[-min_len2:]
    signal_line = signal_line[-min_len2:]
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist

def rsi(values: List[float], period: int = 14) -> List[float]:
    if len(values) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(values)):
        change = values[i] - values[i-1]
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis = [None] * period
    for i in range(period, len(values)-1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100 - (100 / (1 + rs)))
    return rsis

def true_range(high: List[float], low: List[float], close: List[float]) -> List[float]:
    TR = []
    for i in range(1, len(close)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )
        TR.append(tr)
    return TR

def atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> List[float]:
    TR = true_range(high, low, close)
    if len(TR) < period:
        return []
    out = []
    atr_prev = sum(TR[:period]) / period
    out = [None] * (period - 1)
    out.append(atr_prev)
    for t in TR[period:]:
        atr_prev = (atr_prev * (period - 1) + t) / period
        out.append(atr_prev)
    return out

def body_strength(open_: float, close_: float, high: float, low: float) -> float:
    rng = max(high - low, 1e-12)
    return abs(close_ - open_) / rng

def ema_gap_pct(ema_fast_val: float, ema_slow_val: float) -> float:
    base = max(abs(ema_slow_val), 1e-12)
    return abs(ema_fast_val - ema_slow_val) / base

def volume_spike_factor(curr_vol: float, avg_vol: float) -> float:
    base = max(avg_vol, 1e-12)
    return curr_vol / base
# ---------------------------
# قوانین 9‌گانه
# ---------------------------
@dataclass
class RuleResult:
    name: str
    passed: bool
    detail: str

def rule_body_strength(bs: float, risk: RiskLevel) -> RuleResult:
    th = RISK_THRESHOLDS[risk]["BS_min"]
    ok = bs >= th
    return RuleResult("کندل قوی 15m", ok, f"BS15={bs:.3f} [حد ≥ {th}]")

def rule_trend_1h(ema21_1h: float, ema55_1h: float, direction: Direction, risk: RiskLevel) -> RuleResult:
    gap = ema_gap_pct(ema21_1h, ema55_1h)
    th = RISK_THRESHOLDS[risk]["ema_gap_1h_pct"]
    if direction == Direction.LONG:
        ok = (ema21_1h > ema55_1h) and (gap >= th)
    else:
        ok = (ema21_1h < ema55_1h) and (gap >= th)
    return RuleResult("روند 1h", ok, f"EMA21 vs EMA55 gap={gap*100:.2f}% [حد ≥ {th*100:.2f}%]")

def rule_context_4h(ema21_4h: float, ema55_4h: float, direction: Direction, risk: RiskLevel) -> RuleResult:
    gap = ema_gap_pct(ema21_4h, ema55_4h)
    th = RISK_THRESHOLDS[risk]["ema_gap_4h_pct"]
    if risk == RiskLevel.HIGH:
        # سطح بالا: صرفاً عدم خلاف شدید (جهت درست ترجیحی + گپ هرچند کم)
        ok = (gap >= th) and ((ema21_4h > ema55_4h) if direction == Direction.LONG else (ema21_4h < ema55_4h))
    else:
        # کم/میانی: الزام به هم‌جهتی روشن
        ok = ((ema21_4h > ema55_4h) if direction == Direction.LONG else (ema21_4h < ema55_4h)) and (gap >= th)
    return RuleResult("روند 4h", ok, f"EMA21 vs EMA55 gap={gap*100:.2f}% [حد ≥ {th*100:.2f}%]")

def rule_macd(hist_value: float, direction: Direction, risk: RiskLevel) -> RuleResult:
    th = RISK_THRESHOLDS[risk]["macd_hist_min"]
    if direction == Direction.LONG:
        ok = hist_value >= th
    else:
        ok = hist_value <= -th
    return RuleResult("MACD هم‌جهت", ok, f"Hist={hist_value:.6f} [حد ≥ {th}] هم‌جهت با {direction.value}")

def rule_rsi(rsi_value: float, direction: Direction, risk: RiskLevel) -> RuleResult:
    up = RISK_THRESHOLDS[risk]["rsi_long"]
    down = RISK_THRESHOLDS[risk]["rsi_short"]
    if direction == Direction.LONG:
        ok = rsi_value >= up
        return RuleResult("RSI هم‌جهت", ok, f"RSI={rsi_value:.2f} [حد لانگ ≥ {up}]")
    else:
        ok = rsi_value <= down
        return RuleResult("RSI هم‌جهت", ok, f"RSI={rsi_value:.2f} [حد شورت ≤ {down}]")

def rule_ema_30m_alignment(price_30m: float, ema21_30m: float, direction: Direction) -> RuleResult:
    if direction == Direction.LONG:
        ok = price_30m >= ema21_30m
    else:
        ok = price_30m <= ema21_30m
    return RuleResult("همسویی EMA21 30m", ok, f"Price={price_30m:.6f}, EMA21={ema21_30m:.6f}")

def rule_volume_spike(spike_factor: float, risk: RiskLevel) -> RuleResult:
    th = RISK_THRESHOLDS[risk]["volume_spike"]
    ok = spike_factor >= th
    return RuleResult("حجم اسپایک", ok, f"VolSpike={spike_factor:.2f}x [حد ≥ {th}x]")

def rule_ema_fast_cross(ema8_30m: float, ema21_30m: float, direction: Direction, risk: RiskLevel) -> RuleResult:
    require_cross = RISK_THRESHOLDS[risk]["ema_fast_cross"]
    if not require_cross:
        return RuleResult("کراس EMA کوتاه", True, "در سطح بالا اجباری نیست")
    if direction == Direction.LONG:
        ok = ema8_30m >= ema21_30m
    else:
        ok = ema8_30m <= ema21_30m
    return RuleResult("کراس EMA کوتاه", ok, f"EMA8 vs EMA21 هم‌جهت با {direction.value}")

def rule_divergence_none(divergence_detected: bool) -> RuleResult:
    ok = not divergence_detected
    return RuleResult("عدم واگرایی", ok, "Divergence=False")
# ---------------------------
# قیمت‌گذاری و ارزیابی قوانین
# ---------------------------
def compute_sl_tp(entry: float, atr_val: float, direction: Direction, risk: RiskLevel) -> Tuple[float, float]:
    stop_mult = RISK_THRESHOLDS[risk]["atr_stop_mult"]
    rr_mult = RISK_THRESHOLDS[risk]["rr_target_mult"]
    if direction == Direction.LONG:
        stop = entry - atr_val * stop_mult
        target = entry + (entry - stop) * rr_mult
    else:
        stop = entry + atr_val * stop_mult
        target = entry - (stop - entry) * rr_mult
    return stop, target

def evaluate_rules(
    symbol: str,
    direction: Direction,
    risk: RiskLevel,
    price_30m: float,
    open_15m: float, close_15m: float, high_15m: float, low_15m: float,
    ema21_30m: float, ema8_30m: float,
    ema21_1h: float, ema55_1h: float,
    ema21_4h: float, ema55_4h: float,
    macd_hist_30m: float,
    rsi_30m: float,
    vol_spike_factor: float,
    divergence_detected: bool,
) -> Tuple[List[RuleResult], int]:
    results = []
    # 1: BS
    bs = body_strength(open_15m, close_15m, high_15m, low_15m)
    results.append(rule_body_strength(bs, risk))
    # 2: Trend 1h
    results.append(rule_trend_1h(ema21_1h, ema55_1h, direction, risk))
    # 3: Context 4h
    results.append(rule_context_4h(ema21_4h, ema55_4h, direction, risk))
    # 4: MACD
    results.append(rule_macd(macd_hist_30m, direction, risk))
    # 5: RSI
    results.append(rule_rsi(rsi_30m, direction, risk))
    # 6: EMA21 30m alignment
    results.append(rule_ema_30m_alignment(price_30m, ema21_30m, direction))
    # 7: Volume spike
    results.append(rule_volume_spike(vol_spike_factor, risk))
    # 8: EMA fast cross (EMA8 vs EMA21)
    results.append(rule_ema_fast_cross(ema8_30m, ema21_30m, direction, risk))
    # 9: No divergence
    results.append(rule_divergence_none(divergence_detected))
    passed_count = sum(1 for r in results if r.passed)
    return results, passed_count
# ---------------------------
# تولید سیگنال و لاگ خروجی
# ---------------------------
def tehran_now_str() -> str:
    # Tehran time UTC+3:30 (no DST assumed here)
    tz = timezone(timedelta(hours=3, minutes=30))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def build_signal_source(
    direction: Direction,
    ema21_30m: float, ema55_30m: float,
    ema21_1h: float, ema55_1h: float,
    ema21_4h: float, ema55_4h: float,
    rsi_5m: float, rsi_15m: float, rsi_30m: float, rsi_1h: float, rsi_4h: float,
    macd_5m: float, hist_5m: float,
    macd_15m: float, hist_15m: float,
    macd_30m: float, hist_30m: float,
    macd_1h: float, hist_1h: float,
    macd_4h: float, hist_4h: float,
    bs15: float,
    rules_passed_names: List[str],
    reasons: List[str]
) -> str:
    parts = []
    parts.append(f"Dir={direction.value} | TF_EMA=30m:EMA21={ema21_30m},30m:EMA55={ema55_30m},1h:EMA21={ema21_1h},1h:EMA55={ema55_1h},4h:EMA21={ema21_4h},4h:EMA55={ema55_4h}")
    parts.append(f" | TF_RSI=5m:RSI={rsi_5m},15m:RSI={rsi_15m},30m:RSI={rsi_30m},1h:RSI={rsi_1h},4h:RSI={rsi_4h}")
    parts.append(f" | TF_MACD=5m:MACD={macd_5m},5m:HIST={hist_5m},15m:MACD={macd_15m},15m:HIST={hist_15m},30m:MACD={macd_30m},30m:HIST={hist_30m},1h:MACD={macd_1h},1h:HIST={hist_1h},4h:MACD={macd_4h},4h:HIST={hist_4h}")
    parts.append(f" | BS15={bs15}")
    parts.append(f" | RulesPassed={';'.join(rules_passed_names)}")
    parts.append(f" | Reasons={'|'.join(reasons)}")
    return "".join(parts)

def select_risk_level(prefer: Optional[RiskLevel] = None) -> RiskLevel:
    # امکان انتخاب دستی؛ در نبود انتخاب، سطح میانی را پیش‌فرض می‌گذاریم
    return prefer or RiskLevel.MEDIUM

def generate_signal(
    symbol: str,
    direction: Direction,
    prefer_risk: Optional[RiskLevel],
    # داده‌ها (نمونه: آخرین مقدار هر تایم‌فریم)
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
    curr_vol: float, avg_vol_30m: float,
    divergence_detected: bool,
    position_size_usd: float = 10.0,
    broker_fee: float = 0.02
) -> Optional[Signal]:
    risk = select_risk_level(prefer_risk)
    vol_spike = volume_spike_factor(curr_vol, avg_vol_30m)

    # ارزیابی قوانین
    rules, passed = evaluate_rules(
        symbol, direction, risk, price_30m,
        open_15m, close_15m, high_15m, low_15m,
        ema21_30m, ema8_30m,
        ema21_1h, ema55_1h,
        ema21_4h, ema55_4h,
        hist_30m, rsi_30m,
        vol_spike, divergence_detected
    )

    min_required = RISK_THRESHOLDS[risk]["min_rules_pass"]
    if passed < min_required:
        return None  # کیفیت کافی ندارد

    # قیمت‌گذاری
    entry_price = price_30m
    stop_loss, take_profit = compute_sl_tp(entry_price, atr_val_30m, direction, risk)

    # ساخت لاگ/منبع سیگنال
    bs15 = body_strength(open_15m, close_15m, high_15m, low_15m)
    rules_passed_names = [r.name for r in rules if r.passed]
    reasons = [r.detail for r in rules]
    signal_source = build_signal_source(
        direction,
        ema21_30m, ema55_30m,
        ema21_1h, ema55_1h,
        ema21_4h, ema55_4h,
        rsi_5m, rsi_15m, rsi_30m, rsi_1h, rsi_4h,
        macd_line_5m, hist_5m, macd_line_15m, hist_15m,
        macd_line_30m, hist_30m, macd_line_1h, hist_1h,
        macd_line_4h, hist_4h,
        bs15,
        rules_passed_names,
        reasons
    )

    issued = tehran_now_str()

    # مقداردهی اولیه فیلدهای اجرایی (پس از معامله واقعی مقداردهی می‌شوند)
    status = "PENDING"
    hit_time_tehran = None
    hit_price = None
    final_pnl_usd = 0.0
    return_pct = 0.0

    return Signal(
        symbol=symbol,
        direction=direction,
        risk_level=risk,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        issued_at_tehran=issued,
        status=status,
        hit_time_tehran=hit_time_tehran,
        hit_price=hit_price,
        broker_fee=broker_fee,
        final_pnl_usd=final_pnl_usd,
        position_size_usd=position_size_usd,
        return_pct=return_pct,
        signal_source=signal_source
    )
# ---------------------------
# به‌روزرسانی وضعیت پس از برخورد TP/STOP
# ---------------------------
def update_hit_status(signal: Signal, last_price: float, now_tehran: Optional[str] = None) -> Signal:
    now_str = now_tehran or tehran_now_str()
    # LONG: TP اگر last_price >= take_profit، STOP اگر last_price <= stop_loss
    # SHORT: TP اگر last_price <= take_profit، STOP اگر last_price >= stop_loss
    hit = None
    if signal.direction == Direction.LONG:
        if last_price >= signal.take_profit:
            hit = "TP_HIT"
        elif last_price <= signal.stop_loss:
            hit = "STOP_HIT"
    else:
        if last_price <= signal.take_profit:
            hit = "TP_HIT"
        elif last_price >= signal.stop_loss:
            hit = "STOP_HIT"

    if hit is None:
        return signal

    # محاسبه بازده ساده (بدون لغزش قیمت و کارمزد پیچیده)
    entry = signal.entry_price
    size = signal.position_size_usd
    fee = signal.broker_fee
    if signal.direction == Direction.LONG:
        pnl_pct = (last_price - entry) / entry
    else:
        pnl_pct = (entry - last_price) / entry

    final_pnl = size * pnl_pct - fee
    signal.status = hit
    signal.hit_time_tehran = now_str
    signal.hit_price = last_price
    signal.final_pnl_usd = round(final_pnl, 6)
    signal.return_pct = round(pnl_pct * 100, 4)
    return signal

# ---------------------------
# خروجی به CSV (سازگار با ساختار فعلی)
# ---------------------------
import csv

CSV_HEADERS = [
    "symbol","direction","risk_level","entry_price","stop_loss","take_profit",
    "issued_at_tehran","status","hit_time_tehran","hit_price","broker_fee",
    "final_pnl_usd","position_size_usd","return_pct","signal_source"
]

def write_signals_to_csv(path: str, signals: List[Signal]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADERS)
        for s in signals:
            w.writerow([
                s.symbol, s.direction.value, s.risk_level.value,
                f"{s.entry_price:.8f}", f"{s.stop_loss:.8f}", f"{s.take_profit:.8f}",
                s.issued_at_tehran, s.status, s.hit_time_tehran or "",
                f"{s.hit_price:.8f}" if s.hit_price is not None else "",
                f"{s.broker_fee:.6f}", f"{s.final_pnl_usd:.6f}",
                f"{s.position_size_usd:.2f}", f"{s.return_pct:.4f}",
                s.signal_source
            ])
