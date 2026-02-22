# monitor_nightly.py
import csv
import os
import time
import requests
import subprocess  # برای git commit/push
import aiohttp
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  # فرض بر این است که config.py این‌ها را دارد

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

logger = logging.getLogger(__name__)

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

# تابع تولید گزارش روزانه - فقط TP_HIT و STOP_HIT محاسبه می‌شوند
def generate_daily_report(date_str):
    path = daily_csv_path(date_str)
    if not os.path.isfile(path):
        return f"⚠️ فایل CSV برای {date_str} یافت نشد."

    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_signals = list(reader)

    # فقط سیگنال‌های hit شده (TP یا SL فعال شده)
    filtered_signals = [
        s for s in all_signals
        if s.get("status") in ["TP_HIT", "STOP_HIT"]
    ]

    hit_count = len(filtered_signals)
    if hit_count == 0:
        return f"📊 برای تاریخ {date_str} هیچ سیگنال hit شده (TP_HIT یا STOP_HIT) وجود ندارد.\n" \
               f"(OPEN و CLOSED_MANUAL در گزارش روزانه نادیده گرفته می‌شوند)"

    # آمار فقط روی hit شده‌ها
    long_count = sum(1 for s in filtered_signals if s.get("direction") == "LONG")
    short_count = sum(1 for s in filtered_signals if s.get("direction") == "SHORT")
    low_risk = sum(1 for s in filtered_signals if s.get("risk_level") == "LOW")
    medium_risk = sum(1 for s in filtered_signals if s.get("risk_level") == "MEDIUM")
    high_risk = sum(1 for s in filtered_signals if s.get("risk_level") == "HIGH")
    tp_hit_count = sum(1 for s in filtered_signals if s.get("status") == "TP_HIT")
    stop_hit_count = sum(1 for s in filtered_signals if s.get("status") == "STOP_HIT")

    # PNL فقط برای hit شده‌ها
    total_pnl = sum(float(s["final_pnl_usd"]) for s in filtered_signals)
    avg_pnl = total_pnl / hit_count
    success_rate = (tp_hit_count / hit_count * 100) if hit_count > 0 else 0.0

    # بهترین و بدترین
    if filtered_signals:
        best_pnl = max(float(s["final_pnl_usd"]) for s in filtered_signals)
        worst_pnl = min(float(s["final_pnl_usd"]) for s in filtered_signals)
        best_symbol = next((s["symbol"] for s in filtered_signals if float(s["final_pnl_usd"]) == best_pnl), "N/A")
        worst_symbol = next((s["symbol"] for s in filtered_signals if float(s["final_pnl_usd"]) == worst_pnl), "N/A")
    else:
        best_pnl = worst_pnl = 0.0
        best_symbol = worst_symbol = "N/A"

    # گزارش شکیل با Markdown
    report = f"📅 **#گزارش روزانه_سیگنال‌های Hit شده - تاریخ: {date_str}**\n\n"
    report += f"🔢 **تعداد سیگنال‌های فعال‌شده (TP یا SL)**: {hit_count}\n"
    report += f"   - 🟢 LONG: {long_count} ({long_count/hit_count*100:.1f}%)\n"
    report += f"   - 🔴 SHORT: {short_count} ({short_count/hit_count*100:.1f}%)\n\n"
    report += f"📊 **سطوح ریسک** (فقط در سیگنال‌های hit شده):\n"
    report += f"   - 🟢 LOW: {low_risk} ({low_risk/hit_count*100:.1f}%)\n"
    report += f"   - 🟡 MEDIUM: {medium_risk} ({medium_risk/hit_count*100:.1f}%)\n"
    report += f"   - 🔴 HIGH: {high_risk} ({high_risk/hit_count*100:.1f}%)\n\n"
    report += f"🛡️ **وضعیت Hit**:\n"
    report += f"   - ✅ TP_HIT: {tp_hit_count} ({tp_hit_count/hit_count*100:.1f}%)\n"
    report += f"   - ❌ STOP_HIT: {stop_hit_count} ({stop_hit_count/hit_count*100:.1f}%)\n\n"
    report += f"💹 **عملکرد مالی (فقط TP_HIT و STOP_HIT)**:\n"
    report += f"   - نرخ موفقیت (TP): {success_rate:.1f}%\n"
    report += f"   - مجموع PNL (USD): {total_pnl:.2f}\n"
    report += f"   - میانگین PNL هر سیگنال hit شده: {avg_pnl:.2f}\n"
    report += f"   - بهترین نتیجه: {best_pnl:.2f} USD (نماد: {best_symbol})\n"
    report += f"   - بدترین نتیجه: {worst_pnl:.2f} USD (نماد: {worst_symbol})\n\n"
    report += f"ℹ️ **نکته مهم**: فقط سیگنال‌هایی که SL یا TP آن‌ها فعال شده در این گزارش محاسبه شده‌اند. سیگنال‌های OPEN و CLOSED_MANUAL کاملاً نادیده گرفته شده‌اند."

    return report

# تابع ارسال به تلگرام
async def send_to_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("⚠️ تنظیمات تلگرام ناقص است")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}

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

def update_csv_rows(date_str):
    path = daily_csv_path(date_str)
    file_exists = os.path.isfile(path)

    if not file_exists:
        print(f"⚠️ فایل روزانه یافت نشد: {path}")
    else:
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

    # ────────────────────────────────────────────────
    # پاکسازی فایل‌های قدیمی‌تر از ۱۰ روز - با روش daily_csv_path
    now_tehran = tehran_now()
    threshold_date = now_tehran - timedelta(days=10)
    threshold_str = threshold_date.strftime("%Y-%m-%d")

    print("\n🗑️ پاکسازی فایل‌های قدیمی‌تر از {threshold_str} ...")

    deleted_count = 0
    kept_count = 0
    invalid_count = 0

    if not os.path.isdir(SIGNALS_DIR):
        print(f"   پوشه {SIGNALS_DIR} وجود ندارد → هیچ فایلی برای حذف نیست")
        return

    for filename in os.listdir(SIGNALS_DIR):
        if not filename.lower().endswith(".csv"):
            continue

        full_path = os.path.join(SIGNALS_DIR, filename)

        try:
            date_part = filename[:-4].strip()
            file_date = datetime.strptime(date_part, "%Y-%m-%d").date()

            if file_date < threshold_date.date():
                os.remove(full_path)
                print(f"   حذف شد → {filename} ({file_date})")
                deleted_count += 1
            else:
                print(f"   نگه داشته شد → {filename} ({file_date})")
                kept_count += 1

        except ValueError:
            print(f"   رد شد (نام فایل نامعتبر) → {filename}")
            invalid_count += 1
        except PermissionError:
            print(f"   خطای مجوز حذف → {filename}")
            invalid_count += 1
        except Exception as e:
            print(f"   خطا در پردازش {filename}: {e}")
            invalid_count += 1

    print(f"\nنتیجه پاکسازی:")
    print(f"   حذف شده: {deleted_count} فایل")
    print(f"   نگه داشته شده: {kept_count} فایل")
    print(f"   نامعتبر / خطادار: {invalid_count} فایل")
    print("="*80)

    # ────────────────────────────────────────────────
    # تولید گزارش روزانه و ارسال به تلگرام
    report = generate_daily_report(date_str)
    print(report)  # نمایش در کنسول
    import asyncio  # برای اجرای async
    asyncio.run(send_to_telegram(report))  # ارسال به تلگرام

    # ────────────────────────────────────────────────
    # خودکار commit و push تغییرات به GitHub (برای Actions)
    if deleted_count > 0:
        print("\n📤 تلاش برای commit و push حذف‌ها به GitHub...")
        try:
            # تنظیم user برای git
            subprocess.run(["git", "config", "--global", "user.name", "GitHub Action"], check=True)
            subprocess.run(["git", "config", "--global", "user.email", "action@github.com"], check=True)

            # stage تغییرات (حذف‌ها)
            subprocess.run(["git", "add", "-u", SIGNALS_DIR], check=True)

            # commit اگر تغییری بود
            commit_output = subprocess.run(["git", "commit", "-m", f"حذف خودکار {deleted_count} فایل قدیمی signals"], capture_output=True, text=True)
            if "nothing to commit" in commit_output.stdout or commit_output.returncode != 0:
                print("⚠️ هیچ تغییری برای commit نبود یا خطا رخ داد")
            else:
                # push به origin (در Actions، GITHUB_TOKEN مدیریت می‌کند)
                subprocess.run(["git", "push", "origin", "HEAD"], check=True)
                print("✅ تغییرات با موفقیت push شد به GitHub")

        except subprocess.CalledProcessError as e:
            print(f"❌ خطا در git command: {e.stderr}")
        except Exception as e:
            print(f"❌ خطای کلی در git push: {e}")

if __name__ == "__main__":
    now_tehran = tehran_now()
    target_date = (now_tehran - timedelta(days=1)).strftime("%Y-%m-%d")
    update_csv_rows(target_date)
