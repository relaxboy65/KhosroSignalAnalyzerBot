import os

# 🔑 تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# ============================================
# تنظیمات پیشرفته سیستم سیگنال (نسخه S8.2)
# ============================================

# آستانه‌های اصلی
ADX_THRESHOLD_LONG = 25              # حداقل ADX برای سیگنال LONG
ADX_THRESHOLD_SHORT = 22             # حداقل ADX برای سیگنال SHORT
SIGNAL_THRESHOLD = 0.55              # حداقل نسبت وزنی برای صدور سیگنال
BS_MAX_THRESHOLD = 0.85              # حداکثر قدرت کندل مجاز (افزایش از 0.75 به 0.85)
MACD_LONG_MEDIUM_THRESHOLD = 0.001   # حداقل MACD برای LONG MEDIUM (کاهش از 0.0015 به 0.001)
RSI_SHORT_MIN = 35                   # حداقل RSI برای SHORT
RANGE_FILTER_DIFF = 0.003            # حداقل فاصله EMA برای فیلتر رنج ترکیبی
RANGE_FILTER_ADX = 22                # حداقل ADX برای فیلتر رنج ترکیبی
MAX_DAILY_SIGNALS = 30               # حداکثر سیگنال در روز

# بازه‌های ممنوعه برای معامله (به وقت تهران)
FORBIDDEN_HOURS_START = 0    # ساعت شروع (۰۰:۰۰)
FORBIDDEN_HOURS_END = 4      # ساعت پایان (۰۴:۰۰)

# ============================================

# ⚖️ سطوح ریسک
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

# 📊 لیست نمادها
SYMBOLS = [
    'XAUT-USDT',
    'BTC-USDT', 'ETH-USDT', 'BNB-USDT', 'SOL-USDT', 'XRP-USDT',
    'ADA-USDT', 'DOGE-USDT', 'DOT-USDT', 'POL-USDT', 'LTC-USDT',
    'TRX-USDT', 'AVAX-USDT', 'ATOM-USDT', 'XLM-USDT', 'NEAR-USDT',
    'APT-USDT', 'ARB-USDT', 'OP-USDT', 'SUI-USDT', 'FIL-USDT'
]

# ⚙️ پارامترهای مدیریت ریسک دینامیک
RISK_PARAMS = {
    'atr_multiplier': 1.2,
    'rr_target': 2.0,
    'swing_lookback': 10,
    'rr_fallback': 2.0
}

# 📊 وزن‌دهی فاکتورها برای هر سطح ریسک
RISK_FACTORS = {
    "LOW": {
        "ADX": 3, "CCI": 2, "SAR": 3, "Stoch": 2, "TF_Big": 4, "Patterns": 2, "RiskMgmt": 4,
        "Volume": 2, "Candles": 2, "EMA": 2, "Confirm": 3, "Pressure": 3
    },
    "MEDIUM": {
        "ADX": 2, "CCI": 3, "SAR": 2, "Stoch": 3, "TF_Big": 3, "Patterns": 3, "RiskMgmt": 3,
        "Volume": 2, "Candles": 2, "EMA": 2, "Confirm": 3, "Pressure": 3
    },
    "HIGH": {
        "ADX": 1, "CCI": 4, "SAR": 1, "Stoch": 4, "TF_Big": 1, "Patterns": 4, "RiskMgmt": 4,
        "Volume": 1, "Candles": 1, "EMA": 1, "Confirm": 2, "Pressure": 2
    }
}

# 📈 آستانه‌های اندیکاتورهای پیشرفته
INDICATOR_THRESHOLDS = {
    "ADX_STRONG": 25,
    "ADX_WEAK": 20,
    "ADX_MEDIUM": 20,
    "CCI_OVERBOUGHT": 100,
    "CCI_OVERSOLD": -100,
    "STOCH_OVERBOUGHT": 80,
    "STOCH_OVERSOLD": 20
}

# 🛡 مدیریت ریسک پیشرفته
ADVANCED_RISK_PARAMS = {
    "LOW": {"stop_loss_factor": 0.5, "take_profit_factor": 1.0, "signal_strength": "Strong"},
    "MEDIUM": {"stop_loss_factor": 1.0, "take_profit_factor": 1.5, "signal_strength": "Normal"},
    "HIGH": {"stop_loss_factor": 1.5, "take_profit_factor": 2.0, "signal_strength": "Aggressive"}
}
