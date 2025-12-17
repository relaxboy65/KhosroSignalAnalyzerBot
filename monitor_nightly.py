# monitor_nightly.py
import csv
import os
import time
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KUCOIN_URL = "https://api.kucoin.com/api/v1/market/candles"

SIGNALS_DIR = "signals"
CSV_HEADERS = [
    "symbol", "direction", "risk_level", "entry_price", "stop_loss", "take_profit",
    "issued_at_tehran", "status", "hit_time_tehran", "hit_price",
    "broker_fee", "final_pnl_usd", "position_size_usd", "return_pct",
    "signal_source"
]

BROKER_FEE_RATE = 0.001  # 0.1% برای هر سمت (ورود یا خروج). می‌توانید تنظیم کنید.
SLIPPAGE_PCT = 0.0005    # 0.05% لغزش احتمالی

def tehran_now():
    return datetime.now(ZoneInfo("Asia/Tehran"))

def tehran_date_str(dt=None):
    tz = ZoneInfo("Asia/Tehran")
    now = datetime.now(tz) if dt is None else dt.astimezone(tz)
    return now.strftime("%Y-%m-%d")

def parse_tehran_time(s):
    tz = ZoneInfo("Asia/Tehran")
    return datetime.fromisoformat(s).replace(tzinfo=tz)

def daily_csv_path(date_str):
    return os.path.join(SIGNALS_DIR, f"{date_str}.csv")

def fetch_kucoin_1m(symbol, start_at_unix, end_at_unix):
    params = {
        "symbol": symbol,
        "type": "1min",
        "startAt": start_at_unix,
        "endAt": end_at_unix
    }
    try:
        r = requests.get(KUCOIN_URL, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json().get("data", [])
            candles = [{
                't': int(c[0]),
                'o': float(c[1]),
                'c': float(c[2]),
                'h': float(c[3]),
                'l': float(c[4]),
                'v': float(c[5])
            } for c in data]
            return list(reversed(candles))
        elif r.status_code == 429:
            time.sleep(10)
            return fetch_kucoin_1m(symbol, start_at_unix, end_at_unix)
    except Exception as e:
        print(f"❌ خطا در دریافت کندل 1m {symbol}: {e}")
    return []

def compute_pnl_usd(direction, entry_price, exit_price, position_size_usd, fee_rate=BROKER_FEE_RATE):
    # کارمزد ورودی + خروجی
    fee_total = position_size_usd * fee_rate * 2.0
    # تغییر قیمت نسبی
    ret_pct = (exit_price - entry_price) / entry_price if direction == "LONG" else (entry_price - exit_price) / entry_price
    gross_pnl = position_size_usd * ret_pct
    net_pnl = gross_pnl - fee_total
    return net_pnl, ret_pct * 100.0, fee_total

def update_csv_rows(date_str):
    path = daily_csv_path(date_str)
    if not os.path.isfile(path):
        print(f"⚠️ فایل روزانه یافت نشد: {path}")
        return

    # خواندن همه ردیف‌ها
    rows = []
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # بازه روز: از 00:00 تا 23:59 تهران همان تاریخ
    tz = ZoneInfo("Asia/Tehran")
    day_start = datetime.fromisoformat(f"{date_str} 00:00:00").replace(tzinfo=tz)
    day_end = datetime.fromisoformat(f"{date_str} 23:59:00").replace(tzinfo=tz)

    # برای هر OPEN، کندل‌های 1m از زمان صدور تا پایان روز را بررسی
    updated_rows = []
    for row in rows:
        status = row["status"]
        if status != "OPEN":
            updated_rows.append(row)
            continue

        symbol = row["symbol"]
        direction = row["direction"]
        entry_price = float(row["entry_price"])
        stop_loss = float(row["stop_loss"])
        take_profit = float(row["take_profit"])
        issued_at = parse_tehran_time(row["issued_at_tehran"])
        position_size_usd = float(row.get("position_size_usd", "10"))

        start_at_unix = int(issued_at.astimezone(ZoneInfo("UTC")).timestamp())
        end_at_unix = int(day_end.astimezone(ZoneInfo("UTC")).timestamp())

        candles = fetch_kucoin_1m(symbol, start_at_unix, end_at_unix)

        hit_status = None
        hit_time_tehran = ""
        hit_price = ""
        exit_price = None

        for c in candles:
            # فیلد زمان به تهران برای ذخیره
            candle_dt_tehran = datetime.fromtimestamp(c['t'], tz).replace(tzinfo=tz)
            high = c['h']
            low = c['l']

            # بررسی برخورد TP/SL بر اساس سایه کندل
            tp_hit = high >= take_profit
            sl_hit = low <= stop_loss

            # قانون تصمیم‌گیری: اگر هر دو رخ دهند، محافظه‌کارانه اولویت با SL
            if sl_hit and tp_hit:
                # انتخاب اولویت بر اساس جهت
                hit_status = "STOP_HIT"
                hit_price = f"{stop_loss:.8f}"
                hit_time_tehran = candle_dt_tehran.strftime("%Y-%m-%d %H:%M:%S")
                exit_price = stop_loss * (1.0 - SLIPPAGE_PCT) if direction == "LONG" else stop_loss * (1.0 + SLIPPAGE_PCT)
                break
            elif sl_hit:
                hit_status = "STOP_HIT"
                hit_price = f"{stop_loss:.8f}"
                hit_time_tehran = candle_dt_tehran.strftime("%Y-%m-%d %H:%M:%S")
                exit_price = stop_loss * (1.0 - SLIPPAGE_PCT) if direction == "LONG" else stop_loss * (1.0 + SLIPPAGE_PCT)
                break
            elif tp_hit:
                hit_status = "TP_HIT"
                hit_price = f"{take_profit:.8f}"
                hit_time_tehran = candle_dt_tehran.strftime("%Y-%m-%d %H:%M:%S")
                exit_price = take_profit * (1.0 + SLIPPAGE_PCT) if direction == "LONG" else take_profit * (1.0 - SLIPPAGE_PCT)
                break

        if hit_status is None:
            # بستن دستی در پایان روز با قیمت Close کندل 23:59
            if candles:
                last_close = candles[-1]['c']
            else:
                # اگر داده‌ای نبود، همان قیمت ورود را در نظر بگیریم (خنثی)
                last_close = entry_price
            hit_status = "CLOSED_MANUAL"
            hit_price = f"{last_close:.8f}"
            hit_time_tehran = day_end.strftime("%Y-%m-%d %H:%M:%S")
            exit_price = last_close

        # محاسبه کارمزد و سود/زیان
        final_pnl_usd, return_pct, broker_fee = compute_pnl_usd(direction, entry_price, exit_price, position_size_usd)

        # آپدیت ردیف
        row["status"] = hit_status
        row["hit_price"] = hit_price
        row["hit_time_tehran"] = hit_time_tehran
        row["broker_fee"] = f"{broker_fee:.6f}"
        row["final_pnl_usd"] = f"{final_pnl_usd:.6f}"
        row["return_pct"] = f"{return_pct:.4f}"

        updated_rows.append(row)

    # نوشتن مجدد فایل CSV
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in updated_rows:
            writer.writerow(r)

    print(f"✅ وضعیت سیگنال‌های {date_str} آپدیت شد: {path}")

if __name__ == "__main__":
    # اجرای در ساعت 02:00 تهران برای روز قبل
    now_tehran = tehran_now()
    target_date = (now_tehran - timedelta(days=1)).strftime("%Y-%m-%d")
    update_csv_rows(target_date)
