import unittest, math, asyncio
from indicators import calculate_ema, calculate_rsi, calculate_macd, calculate_atr, calculate_adx, calculate_stochastic
from backtest import prepare, run_symbol, report
from rules import analyze_market
from smc import (order_flow_score, volume_profile_score, sweep_score, fvg_score,
                 fibonacci_score, moving_average_score, macd_score, rsi_score)
from ai_committee import _extract_json, _normalize_vote, build_user_prompt


def candles(n=3200, start=100.0):
    out=[]
    for i in range(n):
        # Smooth uptrend with controlled pullbacks and rising volume.
        close=start + i*0.08 + 1.5*math.sin(i/7.0)
        open_=close-0.25 if i%3 else close+0.10
        high=max(open_,close)+0.45
        low=min(open_,close)-0.45
        out.append({'t':i*300,'o':open_,'h':high,'l':low,'c':close,'v':1000+i*2})
    return out

class StrategyTests(unittest.TestCase):
    def test_indicators_are_finite(self):
        c=candles()
        closes=[x['c'] for x in c]
        self.assertTrue(math.isfinite(calculate_ema(closes,21)))
        self.assertTrue(0 <= calculate_rsi(closes) <= 100)
        self.assertTrue(math.isfinite(calculate_macd(closes)['histogram']))
        self.assertTrue(calculate_atr(c)>0)
        adx, p, m=calculate_adx(c)
        self.assertTrue(all(math.isfinite(x) for x in (adx,p,m)))
        k,d=calculate_stochastic(c)
        self.assertTrue(0<=k<=100 and 0<=d<=100)

    def test_analyzer_shape(self):
        data=prepare(candles())
        result=analyze_market('BTC-USDT',data,'LONG')
        self.assertIn(result['status'],('SIGNAL','NO_SIGNAL'))
        self.assertIn('components',result)
        self.assertEqual(len(result['components']),12)
        self.assertIn('rule_score',result)
        names={c['name'] for c in result['components']}
        self.assertEqual(names,{'ai_committee','order_flow','volume_profile','sweep','liquidity',
                                'fvg','fibonacci','supply_demand','moving_average','macd','rsi','pattern'})

    def test_weights_priority_order(self):
        from config import WEIGHTS
        vals=list(WEIGHTS.values())
        self.assertEqual(sum(vals),100)
        self.assertEqual(vals,sorted(vals,reverse=True))
        self.assertEqual(WEIGHTS['ai_committee'],max(vals))

    def test_smc_components_finite(self):
        c=candles(400)
        for direction in ('LONG','SHORT'):
            for fn in (order_flow_score, volume_profile_score, sweep_score,
                       fvg_score, fibonacci_score, moving_average_score,
                       macd_score, rsi_score):
                score,detail=fn(c,direction)
                self.assertTrue(0.0<=score<=1.0, f'{fn.__name__} score {score}')
                self.assertTrue(len(detail)>0)

    def test_order_flow_direction_symmetry(self):
        c=candles(400)
        up,_=order_flow_score(c,'LONG')
        down,_=order_flow_score(c,'SHORT')
        self.assertAlmostEqual(up+down,1.0,places=6)

    def test_extract_json_robust(self):
        self.assertEqual(_extract_json('{"decision":"approve","confidence":80}')['confidence'],80)
        self.assertEqual(_extract_json('```json\n{"decision":"reject","confidence":90}\n```')['decision'],'reject')
        self.assertEqual(_extract_json('blah {"decision":"approve","confidence":55} trailing')['confidence'],55)
        self.assertIsNone(_extract_json('no json here'))
        self.assertEqual(_normalize_vote({'decision':'APPROVE','confidence':'75'}),(True,75.0))
        self.assertEqual(_normalize_vote({'decision':'reject','confidence':70}),(False,70.0))
        self.assertIsNone(_normalize_vote({'decision':'maybe','confidence':50}))

    def test_build_prompt_contains_components(self):
        data=prepare(candles())
        result=analyze_market('BTC-USDT',data,'LONG')
        result['custom_rules']='test rule'
        prompt=build_user_prompt(result)
        self.assertIn('order_flow',prompt)
        self.assertIn('test rule',prompt)
        self.assertIn('BTC-USDT',prompt)

    def test_backtest_runs(self):
        trades=run_symbol('BTC-USDT',candles())
        rep=report(trades)
        self.assertIsInstance(rep,dict)
        self.assertGreaterEqual(rep.get('trades',0),0)

if __name__=='__main__': unittest.main()

class CandleStoreTests(unittest.TestCase):
    def test_sqlite_roundtrip_and_prune(self):
        import tempfile, os, time
        from candle_store import upsert_candles, load_candles, prune_old_candles, database_stats
        import candle_store
        fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
        old = candle_store.CANDLE_DB_PATH
        candle_store.CANDLE_DB_PATH = path
        try:
            now = int(time.time())
            upsert_candles({'BTC-USDT': [
                {'t': now-60, 'o':100, 'h':101, 'l':99, 'c':100.5, 'v':12},
                {'t': now, 'o':100.5, 'h':102, 'l':100, 'c':101, 'v':15},
            ]})
            self.assertEqual(len(load_candles('BTC-USDT')), 2)
            self.assertEqual(database_stats()['candles'], 2)
            deleted = prune_old_candles(now_epoch=now, retention_days=0)
            self.assertEqual(deleted, 1)
        finally:
            candle_store.CANDLE_DB_PATH = old
            os.remove(path)

class OneMinuteBacktestTests(unittest.TestCase):
    def test_one_minute_execution_path(self):
        # Enough 1m history to build the higher timeframes used by the engine.
        c=[]
        for i in range(3600):
            px=100 + i*0.01
            c.append({'t':i*60,'o':px,'h':px+0.2,'l':px-0.2,'c':px+0.05,'v':1000})
        trades=run_symbol('BTC-USDT', c, max_bars=20)
        self.assertIsInstance(trades, list)
