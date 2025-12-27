# signal_store.py
import os
import csv
from datetime import datetime
from zoneinfo import ZoneInfo

# پوشه ذخیره‌سازی
SIGNALS_DIR = "signals"

# ستون‌های CSV روزانه
CSV_HEADERS = [
    "symbol", "direction", "risk_level", "entry_price", "stop_loss", "take_profit",
    "issued_at_tehran", "status", "hit_time_tehran", "hit_price",
    "broker_fee", "final_pnl_usd", "position_size_usd", "return_pct",
    "signal_source", "details", "passed_rules"   # 👈 ستون‌های جدید
]


def ensure_dir():
    if not os.path.isdir(SIGNALS_DIR):
        os.makedirs(SIGNALS_DIR, exist_ok=True)

def tehran_date_str(dt=None):
    tz = ZoneInfo("Asia/Tehran")
    now = datetime.now(tz) if dt is None else dt.astimezone(tz)
    return now.strftime("%Y-%m-%d")

def tehran_time_str(dt=None):
    tz = ZoneInfo("Asia/Tehran")
    now = datetime.now(tz) if dt is None else dt.astimezone(tz)
    return now.strftime("%Y-%m-%d %H:%M:%S")

def daily_csv_path(date_str=None):
    ensure_dir()
    d = tehran_date_str() if date_str is None else date_str
    return os.path.join(SIGNALS_DIR, f"{d}.csv")

def compose_signal_source(check_result, analysis_data, direction):
    # ساخت منبع سیگنال کامل برای تحلیل‌های بعدی
    # Indicators: EMA21/EMA55/MACD/RSI + مقادیر اخیر در تایم‌فریم‌های کلیدی
    closes = analysis_data.get("closes", {})
    tf_indicators = []

    def latest_val(series):
        return round(series[-1], 6) if series and series[-1] is not None else None

    # برای سادگی، فقط آخرین EMA21/EMA55 از 30m و 1h را اضافه می‌کنیم اگر موجود باشند
    from indicators import calculate_ema, calculate_rsi, calculate_macd, body_strength

    ema_parts = []
    for tf in ["30m", "1h", "4h"]:
        if tf in closes and len(closes[tf]) >= 55:
            ema21 = calculate_ema(closes[tf], 21)
            ema55 = calculate_ema(closes[tf], 55) if len(closes[tf]) >= 55 else None
            ema_parts.append(f"{tf}:EMA21={round(ema21,6) if ema21 is not None else 'NA'}")
            ema_parts.append(f"{tf}:EMA55={round(ema55,6) if ema55 is not None else 'NA'}")

    rsi_parts = []
    for tf in ["5m", "15m", "30m", "1h", "4h"]:
        if tf in closes and len(closes[tf]) >= 15:
            rsi = calculate_rsi(closes[tf])
            rsi_parts.append(f"{tf}:RSI={round(rsi,2) if rsi is not None else 'NA'}")

    macd_parts = []
    for tf in ["5m", "15m", "30m", "1h", "4h"]:
        if tf in closes and len(closes[tf]) >= 35:
            macd_obj = calculate_macd(closes[tf])
            mh = macd_obj.get("histogram")
            ml = macd_obj.get("macd")
            macd_parts.append(f"{tf}:MACD={round(ml,6) if ml is not None else 'NA'}")
            macd_parts.append(f"{tf}:HIST={round(mh,6) if mh is not None else 'NA'}")

    # قدرت کندل 15m آخر
    cs15 = None
    if "15m" in analysis_data.get("data", {}) and len(analysis_data["data"]["15m"]) >= 1:
        cs15 = body_strength(analysis_data["data"]["15m"][-1])

    # قوانین پاس‌شده از check_result
    rules_passed = check_result.get("passed_rules", [])
    passed_str = ";".join(rules_passed) if rules_passed else ""

    # شمارش‌های RSI/MACD از متن reasons (به‌صورت آزاد)
    reasons = check_result.get("reasons", [])
    reasons_str = "|".join(reasons) if reasons else ""

    parts = [
        f"Dir={direction}",
        f"TF_EMA={','.join(ema_parts)}" if ema_parts else "TF_EMA=NA",
        f"TF_RSI={','.join(rsi_parts)}" if rsi_parts else "TF_RSI=NA",
        f"TF_MACD={','.join(macd_parts)}" if macd_parts else "TF_MACD=NA",
        f"BS15={round(cs15,3) if cs15 is not None else 'NA'}",
        f"RulesPassed={passed_str}",
        f"Reasons={reasons_str}"
    ]
    return " | ".join(parts)

def append_signal_row(
    symbol, direction, risk_level_name, entry_price, stop_loss, take_profit,
    issued_at_tehran, signal_source, position_size_usd=10.0,
    details="", passed_rules=""
):
    path = daily_csv_path()
    file_exists = os.path.isfile(path)

    row = {
        "symbol": symbol,
        "direction": direction,
        "risk_level": risk_level_name,
        "entry_price": f"{entry_price:.8f}",
        "stop_loss": f"{stop_loss:.8f}",
        "take_profit": f"{take_profit:.8f}",
        "issued_at_tehran": issued_at_tehran,
        "status": "OPEN",
        "hit_time_tehran": "",
        "hit_price": "",
        "broker_fee": "",
        "final_pnl_usd": "",
        "position_size_usd": f"{position_size_usd:.2f}",
        "return_pct": "",
        "signal_source": signal_source,
        "details": details,           # 👈 اضافه شد
        "passed_rules": passed_rules  # 👈 اضافه شد
    }

    with open(path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return path


    # نوشتن CSV
    with open(path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return path
