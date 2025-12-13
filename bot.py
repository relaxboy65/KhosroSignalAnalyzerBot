import requests, time
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SYMBOLS, RISK_LEVELS
from data_fetcher import fetch_all_timeframes
from indicators import calculate_rsi, calculate_ema
from rules import check_rules_for_level

def send_signal(symbol, analysis_data, check_result, direction):
    clean_symbol = symbol.replace('-USDT','')
    emoji = check_result['emoji']
    dir_emoji = '📈' if direction=='LONG' else '📉'
    last_close = analysis_data['last_close']
    stop = last_close*0.985 if direction=='LONG' else last_close*1.015
    target = last_close*1.03 if direction=='LONG' else last_close*0.97
    msg = f"""{emoji} سیگنال {check_result['risk_name']} {dir_emoji}
نماد: {clean_symbol}
قوانین گذرانده: {check_result['passed_count']}
دلایل: {', '.join(check_result['reasons'])}
ورود: {last_close:.2f} | استاپ: {stop:.2f} | تارگت: {target:.2f}
⏰ {datetime.now().strftime('%H:%M:%S')}"""
    url=f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload={"chat_id":TELEGRAM_CHAT_ID,"text":msg}
    requests.post(url,json=payload)

def process_symbol(symbol):
    data=fetch_all_timeframes(symbol)
    if not data: return
    closes={tf:[c[2] for c in data[tf]] for tf in data}
    analysis={'last_close':closes['5m'][-1],'closes':closes}
    for direction in ['LONG','SHORT']:
        for risk in RISK_LEVELS:
            res=check_rules_for_level(analysis,risk,direction)
            if res['passed']:
                send_signal(symbol,analysis,res,direction)
                return

def main():
    for sym in SYMBOLS:
        process_symbol(sym)
        time.sleep(5)

if __name__=="__main__":
    main()
