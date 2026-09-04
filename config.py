import os

VERSION = "10.3.0"
STRATEGY_NAME = "Khosro Confluence Engine"
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

SYMBOLS = [
    'BTC-USDT','ETH-USDT','BNB-USDT','SOL-USDT','XRP-USDT','ADA-USDT','DOGE-USDT',
    'DOT-USDT','POL-USDT','LTC-USDT','TRX-USDT','AVAX-USDT','ATOM-USDT','XLM-USDT',
    'NEAR-USDT','APT-USDT','ARB-USDT','OP-USDT','SUI-USDT','FIL-USDT','XAUT-USDT'
]

TIMEFRAMES = ('5m','15m','30m','1h','4h')
RESOLUTION_TIMEFRAME = '1m'
RESOLUTION_LOOKBACK_DAYS = 10
# Rolling local SQLite market-data cache for later 1m backtests.
CANDLE_DB_PATH = os.getenv('CANDLE_DB_PATH', 'market_data.db')
CANDLE_RETENTION_DAYS = 90
TELEGRAM_MIN_INTERVAL_SECONDS = 3.20
TELEGRAM_MAX_RETRIES = 5
BASE_TIMEFRAME = '30m'
FORBIDDEN_HOURS_START = 0
FORBIDDEN_HOURS_END = 4
MAX_DAILY_SIGNALS = 30
COOLDOWN_BARS = 2

# UpsideGPT-inspired architecture: trend -> levels -> momentum -> volume -> pattern -> risk.
WEIGHTS = {
    'trend_4h': 18,
    'trend_1h': 15,
    'structure_30m': 12,
    'level': 14,
    'momentum': 12,
    'volume': 8,
    'pattern': 8,
    'volatility': 5,
    'mtf_alignment': 8,
}

THRESHOLDS = {
    'low_score': 78,
    'medium_score': 68,
    'signal_score': 64,
    'strong_adx': 25,
    'weak_adx': 18,
    'volume_ratio': 1.20,
    'level_tolerance': 0.004,
    'max_atr_pct': 0.06,
    'min_rr': 2.0,
}

RISK_PARAMS = {
    'LOW': {'atr_sl': 1.4, 'rr': 2.4},
    'MEDIUM': {'atr_sl': 1.6, 'rr': 2.1},
    'HIGH': {'atr_sl': 1.9, 'rr': 2.0},
}

BROKER_FEE_RATE = 0.001
SLIPPAGE_PCT = 0.0005
POSITION_SIZE_USD = 10.0
# Per-signal capital model: $10 margin opened with 10x leverage = $100 notional.
MARGIN_USD = 10.0
LEVERAGE = 10.0
NOTIONAL_USD = MARGIN_USD * LEVERAGE
