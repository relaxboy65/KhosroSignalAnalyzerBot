import aiohttp
import asyncio
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS

KUCOIN_URL = "https://api.kucoin.com/api/v1/market/candles"

# ========== دریافت داده برای یک نماد ==========
async def fetch_symbol(session, symbol, interval="5min", days=3):
    try:
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - days*24*3600
        params = {"symbol": symbol, "type": interval, "startAt": start_time, "endAt": end_time}
        async with session.get(KUCOIN_URL, params=params, timeout=20) as resp:
            if resp.status == 200:
                data = await resp.json()
                candles = data.get("data", [])
                if candles and len(candles) >= 50:
                    return symbol, True
                else:
                    return symbol, False
            else:
                return symbol, False
    except Exception:
        return symbol, False

# ========== ارسال پیام تلگرام ==========
async def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)

# ========== اجرای اصلی ==========
async def main_async():
    start = time.perf_counter()
    server_start = datetime.now()
    tehran_start = datetime.now(ZoneInfo("Asia/Tehran"))

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_symbol(session, sym) for sym in SYMBOLS]
        results = await asyncio.gather(*tasks)

    ok = [sym for sym, status in results if status]
    fail = [sym for sym, status in results if not status]

    duration = time.perf_counter() - start
    server_end = datetime.now()
    tehran_end = datetime.now(ZoneInfo("Asia/Tehran"))

    msg = (
        "📊 گزارش اجرای ربات\n"
        f"⏰ زمان شروع (سرور): {server_start.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏰ زمان شروع (تهران): {tehran_start.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"✅ ارزهای کامل: {', '.join(ok) if ok else 'هیچکدام'}\n"
        f"❌ ارزهای ناقص: {', '.join(fail) if fail else 'هیچکدام'}\n"
        f"⏱ مدت اجرا: {duration:.2f} ثانیه\n"
        f"⏰ پایان (سرور): {server_end.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏰ پایان (تهران): {tehran_end.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    print("="*80)
    print(msg)
    print("="*80)

    await send_telegram(msg)

# ========== اجرا ==========
if __name__ == "__main__":
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ تنظیمات تلگرام را بررسی کنید!")
    else:
        asyncio.run(main_async())
