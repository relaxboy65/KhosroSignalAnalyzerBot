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

BROKER_FEE_RATE = 0.001  # 0.1% برای ورود و خروج
SLIPPAGE_PCT = 0.0005    # 0.05% لغزش

def tehran_now():
    return datetime.now(ZoneInfo("Asia/Tehran"))

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
            print(f"⚠️ Rate limit برای {symbol} — ۱۰ ثانیه صبر...")
            time.sleep(10)
            return fetch_kucoin_1m(symbol, start_at_unix, end_at_unix)
        else:
            print(f"❌ خطای HTTP {r.status_code} برای {symbol}")
    except Exception as e:
        print(f"❌ خطا در دریافت کندل 1m {symbol}: {e}")
    return []

def compute_pnl_usd(direction, entry_price, exit_price, position_size_usd, fee_rate=BROKER_FEE_RATE):
    fee_total = position_size_usd * fee_rate * 2.0
    ret_pct = (exit_price - entry_price) / entry_price if direction == "LONG" else (entry_price - exit_price) / entry_price
    gross_pnl = position_size_usd * ret_pct
    net_pnl = gross_pnl - fee_total
    return net_pnl, ret_pct * 100.0, fee_total
def update_csv_rows(date_str):
    path = daily_csv_path(date_str)
    if not os.path.isfile(path):
        print(f"⚠️ فایل روزانه یافت نشد: {path}")
        return

    rows = []
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    tz = ZoneInfo("Asia/Tehran")
    day_end = datetime.fromisoformat(f"{date_str} 23:59:00").replace(tzinfo=tz)

    print("="*80)
    print(f"📊 شروع مانیتور شبانه برای تاریخ {date_str}")
    print("="*80)

    updated_rows = []
    for row in rows:
        if row["status"] != "OPEN":
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

        print(f"\n🔎 بررسی سیگنال {symbol} ({direction})")
        print(f"زمان صدور: {issued_at} | ورود: {entry_price:.6f} | SL: {stop_loss:.6f} | TP: {take_profit:.6f}")
        print(f"تعداد کندل‌های دریافت‌شده: {len(candles)}")

        if candles:
            first_dt = datetime.fromtimestamp(candles[0]['t'], tz)
            last_dt = datetime.fromtimestamp(candles[-1]['t'], tz)
            print(f"اولین کندل: {first_dt} | آخرین کندل: {last_dt}")
        else:
            print(f"⚠️ هیچ کندلی برای {symbol} دریافت نشد")

        hit_status, hit_time_tehran, hit_price, exit_price = None, "", "", None
        for c in candles:
            candle_dt_tehran = datetime.fromtimestamp(c['t'], tz)
            high, low = c['h'], c['l']
            tp_hit, sl_hit = high >= take_profit, low <= stop_loss

            if sl_hit and tp_hit:
                hit_status = "STOP_HIT"
                hit_price = f"{stop_loss:.8f}"
                hit_time_tehran = candle_dt_tehran.strftime("%Y-%m-%d %H:%M:%S")
                exit_price = stop_loss
                print(f"⚠️ همزمان TP و SL → انتخاب STOP_HIT در {hit_time_tehran}")
                break
            elif sl_hit:
                hit_status = "STOP_HIT"
                hit_price = f"{stop_loss:.8f}"
                hit_time_tehran = candle_dt_tehran.strftime("%Y-%m-%d %H:%M:%S")
                exit_price = stop_loss
                print(f"❌ SL فعال شد در {hit_time_tehran} قیمت {hit_price}")
                break
            elif tp_hit:
                hit_status = "TP_HIT"
                hit_price = f"{take_profit:.8f}"
                hit_time_tehran = candle_dt_tehran.strftime("%Y-%m-%d %H:%M:%S")
                exit_price = take_profit
                print(f"✅ TP فعال شد در {hit_time_tehran} قیمت {hit_price}")
                break

        if hit_status is None:
            last_close = candles[-1]['c'] if candles else entry_price
            hit_status = "CLOSED_MANUAL"
            hit_price = f"{last_close:.8f}"
            hit_time_tehran = day_end.strftime("%Y-%m-%d %H:%M:%S")
            exit_price = last_close
            print(f"📭 سیگنال دستی بسته شد در پایان روز {hit_time_tehran} قیمت {hit_price}")

        final_pnl_usd, return_pct, broker_fee = compute_pnl_usd(direction, entry_price, exit_price, position_size_usd)
        print(f"📈 نتیجه: {hit_status} | سود/زیان نهایی: {final_pnl_usd:.4f} USD | بازده: {return_pct:.2f}% | کارمزد: {broker_fee:.4f} USD")

        row.update({
            "status": hit_status,
            "hit_price": hit_price,
            "hit_time_tehran": hit_time_tehran,
            "broker_fee": f"{broker_fee:.6f}",
            "final_pnl_usd": f"{final_pnl_usd:.6f}",
            "return_pct": f"{return_pct:.4f}"
        })
        updated_rows.append(row)

    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(updated_rows)

    print("="*80)
    print(f"✅ وضعیت سیگنال‌های {date_str} آپدیت شد: {path}")
    print("="*80)


#if __name__ == "__main__":
#    now_tehran = tehran_now()
    # برای تست روز جاری را بررسی کن
#    target_date = now_tehran.strftime("%Y-%m-%d")
#    update_csv_rows(target_date)
    
if __name__ == "__main__":
    now_tehran = tehran_now()
    target_date = (now_tehran - timedelta(days=1)).strftime("%Y-%m-%d")
    update_csv_rows(target_date)

