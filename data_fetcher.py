import requests
import time
from datetime import datetime, timedelta

def fetch_kucoin_klines(symbol, interval='5min', days=3):
    interval_map = {
        '5m': '5min', '15m': '15min', '30m': '30min',
        '1h': '1hour', '4h': '4hour'
    }
    kucoin_interval = interval_map.get(interval, interval)
    end_time = int(datetime.utcnow().timestamp())
    start_time = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    url = "https://api.kucoin.com/api/v1/market/candles"
    params = {'symbol': symbol, 'type': kucoin_interval,
              'startAt': start_time, 'endAt': end_time}
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code == 200:
            data = r.json().get('data', [])
            # خروجی به شکل دیکشنری
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
            return fetch_kucoin_klines(symbol, interval, days)
    except Exception as e:
        print(f"❌ خطا در دریافت داده {symbol}: {e}")
    return None

def fetch_all_timeframes(symbol):
    settings = {'5m':3, '15m':3, '30m':7, '1h':15, '4h':30}
    data = {}
    for tf, days in settings.items():
        candles = fetch_kucoin_klines(symbol, tf, days)
        if candles and len(candles) >= 50:
            data[tf] = candles
    return data
