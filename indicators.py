import requests, time
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
            candles = [[int(c[0]), float(c[1]), float(c[2]),
                        float(c[3]), float(c[4]), float(c[5])] for c in data]
            return list(reversed(candles))
    except: pass
    return None

def fetch_all_timeframes(symbol):
    settings = {'5m':3, '15m':3, '30m':7, '1h':15, '4h':30}
    data = {}
    for tf, days in settings.items():
        candles = fetch_kucoin_klines(symbol, tf, days)
        if candles: data[tf] = candles
    return data

# اندیکاتورها
def calculate_ema(prices, period):
    if len(prices) < period: return None
    k = 2/(period+1); ema = sum(prices[:period])/period
    for p in prices[period:]: ema = (p-ema)*k+ema
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period+1: return None
    gains, losses = [], []
    for i in range(1,len(prices)):
        diff = prices[i]-prices[i-1]
        gains.append(max(diff,0)); losses.append(max(-diff,0))
    avg_gain=sum(gains[:period])/period; avg_loss=sum(losses[:period])/period
    if avg_loss==0: return 100
    rs=avg_gain/avg_loss; return 100-(100/(1+rs))
