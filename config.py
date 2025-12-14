import os

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RISK_LEVELS = [
    {
        'key': 'LOW',
        'name': 'ریسک کم',
        'emoji': '🟢',
        'rules': {
            'trend_4h_emas': [21, 55, 200],
            'trend_1h_emas': [21, 55],
            'candle_15m_strength': 0.6,
            'candle_5m_strength': 0.6,
            'rsi_threshold_count': 5,
            'macd_threshold_count': 5,
            'entry_break_threshold': 0.0,
        }
    },
    {
        'key': 'MEDIUM',
        'name': 'ریسک میانی',
        'emoji': '🟡',
        'rules': {
            'trend_4h_emas': [21, 55],
            'trend_1h_emas': [21, 55],
            'candle_15m_strength': 0.48,
            'candle_5m_strength': 0.48,
            'rsi_threshold_count': 4,
            'macd_threshold_count': 4,
            'entry_break_threshold': 0.003,
        }
    },
    {
        'key': 'HIGH',
        'name': 'ریسک بالا',
        'emoji': '🔴',
        'rules': {
            'trend_4h_emas': [21],
            'trend_1h_emas': [21, 55],
            'candle_15m_strength': 0.35,
            'candle_5m_strength': 0.35,
            'rsi_threshold_count': 3,
            'macd_threshold_count': 3,
            'entry_break_threshold': 0.003,
        }
    }
]

SYMBOLS = [
    'XAUT-USDT', 'KAG-USDT',
    'BTC-USDT', 'ETH-USDT', 'BNB-USDT', 'SOL-USDT', 'XRP-USDT',
    'ADA-USDT', 'DOGE-USDT', 'DOT-USDT', 'POL-USDT', 'LTC-USDT',
    'TRX-USDT', 'AVAX-USDT', 'ATOM-USDT', 'XLM-USDT', 'NEAR-USDT',
    'APT-USDT', 'ARB-USDT', 'OP-USDT', 'SUI-USDT', 'FIL-USDT'
]

# پارامترهای مدیریت ریسک دینامیک
RISK_PARAMS = {
    'atr_multiplier': 1.2,   # فاصله استاپ از ورود بر اساس ATR
    'rr_target': 2.0,        # نسبت هدف به ریسک
    'swing_lookback': 10,    # نگاه به 10 کندل اخیر برای Swing
    'rr_fallback': 2.0       # اگر ATR نباشد، RR بر اساس Swing
}
