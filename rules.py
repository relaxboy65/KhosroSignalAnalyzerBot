from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Optional
import aiohttp

from config import (
    VERSION, STRATEGY_NAME, WEIGHTS, THRESHOLDS, RISK_PARAMS,
    MAX_DAILY_SIGNALS, FORBIDDEN_HOURS_START, FORBIDDEN_HOURS_END,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MARGIN_USD, LEVERAGE
)
from indicators import calculate_ema, calculate_rsi, calculate_macd, calculate_atr, calculate_adx, find_pivots
from patterns import candle_pattern, ema_rejection, breakout_or_retest
from signal_store import append_signal_row, tehran_time_str

logger = logging.getLogger(__name__)
_daily_signal_count = 0
_daily_signal_date = None

@dataclass
class Component:
    name: str
    score: float
    weight: float
    detail: str

    @property
    def contribution(self):
        return self.score * self.weight


def _reset_daily():
    global _daily_signal_count, _daily_signal_date
    d = datetime.now(ZoneInfo('Asia/Tehran')).date()
    if d != _daily_signal_date:
        _daily_signal_date, _daily_signal_count = d, 0


def can_issue_signal():
    global _daily_signal_count
    _reset_daily()
    if _daily_signal_count >= MAX_DAILY_SIGNALS:
        return False
    _daily_signal_count += 1
    return True


def is_forbidden_hour():
    h = datetime.now(ZoneInfo('Asia/Tehran')).hour
    return FORBIDDEN_HOURS_START <= h < FORBIDDEN_HOURS_END


def _tf_state(candles, direction, ema_fast=21, ema_slow=55):
    if len(candles) < ema_slow + 5:
        return 0.0, 'insufficient data'
    closes = [x['c'] for x in candles]
    ef, es = calculate_ema(closes, ema_fast), calculate_ema(closes, ema_slow)
    price = closes[-1]
    adx, pdi, mdi = calculate_adx(candles)
    score = 0.0
    if direction == 'LONG':
        score += 0.5 if ef > es else 0
        score += 0.35 if price > ef else 0
        score += 0.15 if pdi is not None and mdi is not None and pdi > mdi else 0
    else:
        score += 0.5 if ef < es else 0
        score += 0.35 if price < ef else 0
        score += 0.15 if pdi is not None and mdi is not None and mdi > pdi else 0
    return score, f'price={price:.6g} EMA{ema_fast}={ef:.6g} EMA{ema_slow}={es:.6g} ADX={adx if adx is not None else 0:.1f}'


def _structure_score(candles, direction):
    if len(candles) < 12:
        return 0.0, 'insufficient data'
    highs, lows = find_pivots(candles[-80:])
    if len(highs) < 2 or len(lows) < 2:
        return 0.35, 'not enough confirmed pivots; neutral'
    h1, h2 = highs[-2][1], highs[-1][1]
    l1, l2 = lows[-2][1], lows[-1][1]
    if direction == 'LONG':
        score = 1.0 if h2 > h1 and l2 > l1 else 0.0 if h2 < h1 and l2 < l1 else 0.5
        detail = f'HH={h2>h1}, HL={l2>l1}'
    else:
        score = 1.0 if h2 < h1 and l2 < l1 else 0.0 if h2 > h1 and l2 > l1 else 0.5
        detail = f'LH={h2<h1}, LL={l2<l1}'
    return score, detail


def _levels(candles):
    highs, lows = find_pivots(candles[-120:])
    return (highs[-1][1] if highs else None), (lows[-1][1] if lows else None)


def _level_score(candles, direction):
    if len(candles) < 30:
        return 0.0, 'insufficient data', None, None
    price = candles[-1]['c']
    resistance, support = _levels(candles)
    tol = THRESHOLDS['level_tolerance']
    if direction == 'LONG':
        level = support
        if level is None:
            return 0.3, 'no support pivot', None, resistance
        dist = abs(price-level)/price
        score = 1.0 if dist <= tol else 0.65 if dist <= tol*2.0 else 0.25
        return score, f'support={level:.6g}, distance={dist:.3%}', level, resistance
    level = resistance
    if level is None:
        return 0.3, 'no resistance pivot', support, None
    dist = abs(price-level)/price
    score = 1.0 if dist <= tol else 0.65 if dist <= tol*2.0 else 0.25
    return score, f'resistance={level:.6g}, distance={dist:.3%}', support, level


def _momentum_score(candles, direction):
    closes = [x['c'] for x in candles]
    rsi = calculate_rsi(closes)
    macd = calculate_macd(closes)
    adx, pdi, mdi = calculate_adx(candles)
    score = 0.0
    details = []
    if rsi is not None:
        if direction == 'LONG':
            score += 0.55 if 50 <= rsi <= 68 else 0.35 if 45 <= rsi < 50 else 0.15 if rsi < 45 else 0.0
        else:
            score += 0.55 if 32 <= rsi <= 50 else 0.35 if 50 < rsi <= 55 else 0.15 if rsi > 55 else 0.0
        details.append(f'RSI={rsi:.1f}')
    hist = macd.get('histogram')
    line, sig = macd.get('macd'), macd.get('signal')
    if hist is not None:
        aligned = hist > 0 if direction == 'LONG' else hist < 0
        score += 0.45 if aligned else 0.0
        details.append(f'MACD_hist={hist:.6g}')
    if adx is not None and pdi is not None and mdi is not None:
        aligned = pdi > mdi if direction == 'LONG' else mdi > pdi
        if adx >= THRESHOLDS['strong_adx'] and aligned:
            score = min(1.0, score + 0.15)
        details.append(f'ADX={adx:.1f}')
    return min(score,1.0), ', '.join(details)


def _volume_score(candles):
    if len(candles) < 21:
        return 0.0, 'insufficient data', 0.0
    cur = candles[-1]['v']
    avg = sum(x['v'] for x in candles[-21:-1]) / 20.0
    ratio = cur / avg if avg else 0.0
    score = 1.0 if ratio >= 1.5 else 0.8 if ratio >= THRESHOLDS['volume_ratio'] else 0.5 if ratio >= 0.9 else 0.2
    return score, f'volume ratio={ratio:.2f}x', ratio


def _pattern_score(candles, direction, level):
    pat = candle_pattern(candles)
    score = 0.35
    if pat:
        bullish = pat in ('HAMMER','BULLISH_ENGULFING')
        bearish = pat in ('SHOOTING_STAR','BEARISH_ENGULFING')
        if (direction == 'LONG' and bullish) or (direction == 'SHORT' and bearish):
            score = 1.0
        elif (direction == 'LONG' and bearish) or (direction == 'SHORT' and bullish):
            score = 0.0
        else:
            score = 0.5
    if level is not None and ema_rejection(candles, level, direction):
        score = min(1.0, score + 0.2)
    return score, f'pattern={pat or "NONE"}'


def _mtf_alignment(data, direction):
    scores=[]
    for tf,w in [('4h',1.0),('1h',0.8),('30m',0.7),('15m',0.45),('5m',0.25)]:
        c=data.get(tf,[])
        if c:
            s,_=_tf_state(c,direction)
            scores.append((s,w))
    if not scores: return 0.0,'no timeframes'
    value=sum(s*w for s,w in scores)/sum(w for _,w in scores)
    return value, f'weighted alignment={value:.2f}'


def _atr_levels(candles, direction, risk):
    price=candles[-1]['c']; atr=calculate_atr(candles)
    if atr is None or atr <= 0: return None,None,None
    p=RISK_PARAMS[risk]
    if direction=='LONG':
        sl=price-atr*p['atr_sl']; tp=price+(price-sl)*p['rr']
    else:
        sl=price+atr*p['atr_sl']; tp=price-(sl-price)*p['rr']
    return sl,tp,atr


def analyze_market(symbol: str, data: Dict[str,list], direction: str, risk_hint='MEDIUM') -> dict:
    base=data.get('30m',[])
    if len(base)<80:
        return {'status':'NO_SIGNAL','reason':'not enough 30m candles','symbol':symbol,'direction':direction}
    comps=[]
    s,d=_tf_state(data.get('4h',[]),direction); comps.append(Component('4h trend',s,WEIGHTS['trend_4h'],d))
    s,d=_tf_state(data.get('1h',[]),direction); comps.append(Component('1h trend',s,WEIGHTS['trend_1h'],d))
    s,d=_structure_score(base,direction); comps.append(Component('30m structure',s,WEIGHTS['structure_30m'],d))
    s,d,support,resistance=_level_score(base,direction); comps.append(Component('key level',s,WEIGHTS['level'],d))
    s,d=_momentum_score(base,direction); comps.append(Component('momentum',s,WEIGHTS['momentum'],d))
    s,d,vol_ratio=_volume_score(base); comps.append(Component('volume',s,WEIGHTS['volume'],d))
    s,d=_pattern_score(base,direction,support if direction=='LONG' else resistance); comps.append(Component('candlestick/pattern',s,WEIGHTS['pattern'],d))
    atr=calculate_atr(base); atr_pct=atr/base[-1]['c'] if atr else 999
    vol_score=1.0 if atr_pct <= 0.025 else 0.7 if atr_pct <= 0.04 else 0.25 if atr_pct <= THRESHOLDS['max_atr_pct'] else 0.0
    comps.append(Component('volatility',vol_score,WEIGHTS['volatility'],f'ATR={atr:.6g} ({atr_pct:.2%})' if atr else 'ATR unavailable'))
    s,d=_mtf_alignment(data,direction); comps.append(Component('multi-timeframe',s,WEIGHTS['mtf_alignment'],d))
    total=sum(c.weight for c in comps)
    score=100*sum(c.contribution for c in comps)/total
    risk='LOW' if score>=THRESHOLDS['low_score'] else 'MEDIUM' if score>=THRESHOLDS['medium_score'] else 'HIGH'
    sl,tp,atr=_atr_levels(base,direction,risk)
    rr=RISK_PARAMS[risk]['rr']
    # Structure-aware improvement: if a meaningful level exists, place stop outside it only when it remains >=2R.
    price=base[-1]['c']
    if direction=='LONG' and support and support < price:
        candidate=support-(atr*0.15 if atr else price*0.001)
        if price-candidate > 0 and (price+(price-candidate)*rr) > price:
            sl=candidate; tp=price+(price-sl)*rr
    if direction=='SHORT' and resistance and resistance > price:
        candidate=resistance+(atr*0.15 if atr else price*0.001)
        if candidate-price > 0:
            sl=candidate; tp=price-(sl-price)*rr
    # Require directional higher-timeframe alignment; do not allow a high score created only by low TF noise.
    trend4=comps[0].score; trend1=comps[1].score
    status='SIGNAL' if score>=THRESHOLDS['signal_score'] and trend4>=0.35 and trend1>=0.35 and sl and tp else 'NO_SIGNAL'
    return {
        'status':status,'symbol':symbol,'direction':direction,'risk':risk,'score':round(score,2),
        'confidence':round(score,1),'price':price,'stop_loss':sl,'take_profit':tp,'atr':atr,
        'support':support,'resistance':resistance,'volume_ratio':vol_ratio,'rr':rr,
        'components':[{'name':c.name,'score':round(c.score,3),'weight':c.weight,'detail':c.detail} for c in comps],
        'signal_source': ' | '.join(f'{c.name}={c.score:.2f}:{c.detail}' for c in comps),
        'version':VERSION,'strategy':STRATEGY_NAME
    }


async def send_to_telegram(text: str, reply_to_message_id=None):
    """Send Telegram messages safely: one shared per-chat queue, 1.10s spacing and 429 retry."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning('Telegram credentials are not configured')
        return None
    import asyncio, json, time
    from config import TELEGRAM_MIN_INTERVAL_SECONDS, TELEGRAM_MAX_RETRIES
    if not hasattr(send_to_telegram, '_lock'):
        send_to_telegram._lock = asyncio.Lock()
        send_to_telegram._last_send = 0.0
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True}
    if reply_to_message_id:
        try:
            payload['reply_parameters'] = {'message_id': int(reply_to_message_id)}
        except (TypeError, ValueError):
            logger.warning('Invalid Telegram reply id: %r', reply_to_message_id)
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    async with send_to_telegram._lock:
        async with aiohttp.ClientSession() as session:
            for attempt in range(TELEGRAM_MAX_RETRIES):
                wait = TELEGRAM_MIN_INTERVAL_SECONDS - (time.monotonic() - send_to_telegram._last_send)
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    async with session.post(url, json=payload, timeout=20) as r:
                        body = await r.text()
                        send_to_telegram._last_send = time.monotonic()
                        try:
                            data = json.loads(body)
                        except Exception:
                            data = {}
                        if r.status == 200 and data.get('ok'):
                            return (data.get('result') or {}).get('message_id')
                        if r.status == 429:
                            retry_after = int((data.get('parameters') or {}).get('retry_after', 5))
                            logger.warning('Telegram 429; retry_after=%ss attempt=%d/%d', retry_after, attempt + 1, TELEGRAM_MAX_RETRIES)
                            await asyncio.sleep(max(retry_after, TELEGRAM_MIN_INTERVAL_SECONDS))
                            continue
                        logger.warning('Telegram HTTP %s: %s', r.status, body)
                        return None
                except Exception as exc:
                    logger.warning('Telegram send error attempt=%d/%d: %s', attempt + 1, TELEGRAM_MAX_RETRIES, exc)
                    if attempt + 1 < TELEGRAM_MAX_RETRIES:
                        await asyncio.sleep(min(2 ** attempt, 8))
    return None


async def generate_signal(symbol, direction, prefer_risk, price_30m, open_15m, close_15m, high_15m, low_15m,
                          open_5m, close_5m, high_5m, low_5m, open_1m, close_1m, high_1m, low_1m,
                          ema21_30m, ema50_30m, ema8_30m, ema21_1h, ema50_1h, ema21_4h, ema50_4h, ema200_4h,
                          macd_line_30m, hist_30m, rsi_30m, atr_val_30m, curr_vol, avg_vol_30m,
                          divergence_detected, candles, prices_series_30m, closes_by_tf):
    if is_forbidden_hour():
        return {'symbol':symbol,'direction':direction,'status':'NO_SIGNAL','reason':'forbidden hour','version':VERSION}
    result=analyze_market(symbol,closes_by_tf,direction,prefer_risk)
    if result.get('status')!='SIGNAL':
        return result
    if not can_issue_signal():
        result['status']='NO_SIGNAL'; result['reason']='daily signal limit reached'; return result
    from telegram_ui import signal_message
    time_str=tehran_time_str()
    result['time']=time_str
    msg=signal_message(result, VERSION, MARGIN_USD, LEVERAGE)
    telegram_id=await send_to_telegram(msg)
    append_signal_row(symbol,direction,result['risk'],result['price'],result['stop_loss'],result['take_profit'],time_str,result['signal_source'],position_margin_usd=MARGIN_USD,leverage=LEVERAGE,telegram_message_id=telegram_id,issued_at_epoch=int(datetime.now(ZoneInfo('UTC')).timestamp()))
    return result
