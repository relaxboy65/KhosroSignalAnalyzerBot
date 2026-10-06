"""v11.2.0 strategy, risk-cap and storage tests (restored + extended)."""
import unittest, math, asyncio, os, tempfile, time, sqlite3
from indicators import calculate_ema, calculate_rsi, calculate_macd, calculate_atr, calculate_adx, calculate_stochastic
from backtest import prepare, run_symbol, report
from rules import analyze_market, _apply_stop_caps, _structural_stop
from smc import (order_flow_score, volume_profile_score, sweep_score, fvg_score,
                 fibonacci_score, supply_demand_score, liquidity_score,
                 moving_average_score, macd_score, rsi_score)
from ai_committee import _extract_json, _normalize_vote, build_user_prompt
from config import (WEIGHTS, THRESHOLDS, RISK_PARAMS, STOP_MAX_PCT, STOP_MIN_PCT,
                    STRUCT_STOP_MAX_ATR, CANDLE_RETENTION_DAYS, RESOLUTION_LOOKBACK_DAYS)


def candles(n=3200, start=100.0, drift=0.08, amp=1.5):
    out=[]
    for i in range(n):
        # Smooth uptrend with controlled pullbacks and rising volume.
        close=start + i*drift + amp*math.sin(i/7.0)
        open_=close-0.25 if i%3 else close+0.10
        high=max(open_,close)+0.45
        low=min(open_,close)-0.45
        out.append({'t':i*300,'o':open_,'h':high,'l':low,'c':close,'v':1000+i*2})
    return out


def mirrored(c):
    """Mirror a series around its prices so an uptrend becomes a downtrend."""
    return [{'t':x['t'],'o':200-x['o'],'h':200-x['l'],'l':200-x['h'],'c':200-x['c'],'v':x['v']} for x in c]


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
        self.assertIn('stop_pct',result)
        self.assertIn('stop_capped',result)
        self.assertIn('score_threshold',result)
        names={c['name'] for c in result['components']}
        self.assertEqual(names,{'ai_committee','order_flow','volume_profile','sweep','liquidity',
                                'fvg','fibonacci','supply_demand','moving_average','macd','rsi','pattern'})

    def test_weights_priority_order(self):
        vals=list(WEIGHTS.values())
        self.assertEqual(sum(vals),100)
        self.assertEqual(vals,sorted(vals,reverse=True))
        self.assertEqual(WEIGHTS['ai_committee'],max(vals))

    def test_config_risk_invariants(self):
        self.assertLess(STOP_MIN_PCT, STOP_MAX_PCT)
        self.assertLessEqual(STOP_MAX_PCT, 0.05)          # worst-case SL loss <= 50% margin
        self.assertGreaterEqual(STRUCT_STOP_MAX_ATR, 1.0)
        # retention must cover the 1m resolution lookback with a small buffer
        self.assertGreaterEqual(CANDLE_RETENTION_DAYS, RESOLUTION_LOOKBACK_DAYS + 1)
        self.assertGreater(THRESHOLDS['short_signal_score'], THRESHOLDS['signal_score'])
        self.assertGreater(THRESHOLDS['short_htf_min'], 0.35)

    def test_stop_caps_bound_distance(self):
        price=100.0
        for atr_pct in (0.002, 0.01, 0.03, 0.06, 0.12):   # includes ATRs above the vol gate
            atr=price*atr_pct
            for direction in ('LONG','SHORT'):
                for risk in ('LOW','MEDIUM','HIGH'):
                    # absurdly far stop must be capped
                    far = price*0.5 if direction=='LONG' else price*1.5
                    capped,capped_flag=_apply_stop_caps(far,price,atr,direction,risk)
                    dist=abs(price-capped)/price
                    self.assertLessEqual(dist, STOP_MAX_PCT+1e-9,
                        f'{direction} {risk} atr%={atr_pct} dist={dist}')
                    self.assertTrue(capped_flag)
                    # absurdly tight stop must be floored
                    tight = price*0.999 if direction=='LONG' else price*1.001
                    floored,_=_apply_stop_caps(tight,price,atr,direction,risk)
                    dist2=abs(price-floored)/price
                    self.assertGreaterEqual(dist2, STOP_MIN_PCT-1e-9)
                    # sanity: stop sits on the correct side of entry
                    if direction=='LONG': self.assertLess(capped,price)
                    else: self.assertGreater(capped,price)

    def test_structural_stop_never_beyond_caps(self):
        # Regression for the v11.1 bug: pivot 6.5% away used to become the SL.
        for direction in ('LONG','SHORT'):
            for pivot_pct in (0.003, 0.01, 0.025, 0.065):
                c=candles(400)
                price=c[-1]['c']
                atr=calculate_atr(c)
                level = price*(1-pivot_pct) if direction=='LONG' else price*(1+pivot_pct)
                cand=_structural_stop(c,direction,level,'MEDIUM')
                if cand is None:
                    continue
                capped,_=_apply_stop_caps(cand,price,atr,direction,'MEDIUM')
                dist=abs(price-capped)/price
                self.assertLessEqual(dist,STOP_MAX_PCT+1e-9,
                    f'{direction} pivot={pivot_pct} dist={dist}')
                self.assertGreaterEqual(dist,STOP_MIN_PCT-1e-9)

    def test_every_signal_stop_is_capped(self):
        for series,dirs in ((candles(),('LONG','SHORT')),(mirrored(candles()),('LONG','SHORT'))):
            data=prepare(series)
            for d in dirs:
                r=analyze_market('BTC-USDT',data,d)
                if r.get('status')!='SIGNAL':
                    continue
                dist=abs(r['price']-r['stop_loss'])/r['price']
                self.assertLessEqual(dist,STOP_MAX_PCT+1e-9)
                self.assertGreaterEqual(dist,STOP_MIN_PCT-1e-9)
                # R:R is preserved exactly after capping
                expected_tp = r['price']+(r['price']-r['stop_loss'])*r['rr'] if d=='LONG' \
                              else r['price']-(r['stop_loss']-r['price'])*r['rr']
                self.assertAlmostEqual(r['take_profit'],expected_tp,places=8)

    def test_short_gates_are_stricter(self):
        # A bearish series: a SHORT that passes the loose LONG-era gates must
        # still respect the higher short score threshold.
        data=prepare(mirrored(candles()))
        r=analyze_market('BTC-USDT',data,'SHORT')
        if r.get('status')=='SIGNAL':
            self.assertGreaterEqual(r['score'],THRESHOLDS['short_signal_score'])
            self.assertGreaterEqual(r.get('gate_4h',1),THRESHOLDS['short_htf_min'])

    def test_short_htf_gate_blocks_weak_bearish_trend(self):
        # Craft 4h/1h series where SHORT trend score lands in [0.35, 0.60):
        # long clean downtrend (EMA fast < slow: +0.5) then a 10-bar recovery
        # rally (price above fast EMA: no +0.35, DI flips bullish: no +0.15).
        # LONG on the same data scores >= 0.35 and would pass — proving the
        # SHORT-only 0.60 threshold is what blocks it.
        def weak_bear():
            out = []; px = 100.0; t = 0
            for _ in range(310):                # persistent downtrend
                px -= 0.010
                o, c = px + 0.012, px - 0.012   # bearish candle bodies
                out.append({'t': t, 'o': o, 'h': max(o, c) + 0.005,
                            'l': min(o, c) - 0.005, 'c': c, 'v': 1000})
                t += 14400
            for _ in range(10):                 # short recovery rally
                px += 0.020
                o, c = px - 0.024, px + 0.024   # bullish candle bodies
                out.append({'t': t, 'o': o, 'h': max(o, c) + 0.01,
                            'l': min(o, c) - 0.01, 'c': c, 'v': 1200})
                t += 14400
            return out
        from rules import _tf_state
        c = weak_bear()
        score, detail = _tf_state(c, 'SHORT')
        self.assertGreaterEqual(score, 0.35, f'needs loose-gate pass to be meaningful: {detail}')
        self.assertLess(score, THRESHOLDS['short_htf_min'],
            f'test data must produce a weak bearish trend, got {score}: {detail}')
        long_score, _ = _tf_state(c, 'LONG')
        self.assertGreaterEqual(long_score, 0.35, 'LONG must pass on the same data')
        data = {'4h': c, '1h': c, '30m': candles(300)}
        r = analyze_market('TEST-USDT', data, 'SHORT')
        self.assertEqual(r['status'], 'NO_SIGNAL')
        self.assertEqual(r.get('reason'), 'htf trend gate')

    def test_smc_components_finite(self):
        c=candles(400)
        for direction in ('LONG','SHORT'):
            for fn in (order_flow_score, volume_profile_score, sweep_score,
                       liquidity_score, fvg_score, fibonacci_score,
                       supply_demand_score, moving_average_score,
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
        # every backtest trade must respect the hard stop cap
        for t in trades:
            self.assertLessEqual(t['ret'], STOP_MAX_PCT*RISK_PARAMS[t['risk']]['rr']+0.05,
                                 'trade return larger than capped risk x RR + fees')


class CandleStoreTests(unittest.TestCase):
    def _use_temp_db(self):
        fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
        import candle_store
        old = candle_store.CANDLE_DB_PATH
        candle_store.CANDLE_DB_PATH = path
        return candle_store, path, old

    def test_sqlite_roundtrip_and_prune(self):
        from candle_store import upsert_candles, load_candles, prune_old_candles, database_stats
        cs, path, old = self._use_temp_db()
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
            self.assertEqual(len(load_candles('BTC-USDT')), 1)
        finally:
            cs.CANDLE_DB_PATH = old
            os.remove(path)

    def test_vacuum_and_size_guard(self):
        from candle_store import upsert_candles, prune_old_candles, enforce_db_size_limit, vacuum_database
        cs, path, old = self._use_temp_db()
        try:
            now = int(time.time())
            bulk=[{'t':now-i*60,'o':100+ (i%50)*0.01,'h':101+(i%50)*0.01,'l':99+(i%50)*0.01,
                   'c':100.5+(i%50)*0.01,'v':10+i%7} for i in range(5000)]
            upsert_candles({'BTC-USDT':bulk})
            size_before=os.path.getsize(path)
            self.assertGreater(size_before,0)
            vacuum_database()
            # enforce with an impossible tiny limit → emergency prune kicks in
            rep=enforce_db_size_limit(now_epoch=now, max_mb=0.0001)
            self.assertTrue(rep['actions'], rep)
            remaining=cs.database_stats()['candles']
            self.assertLess(remaining,5000)
            # file must still be a valid, queryable sqlite db
            conn=sqlite3.connect(path)
            n=conn.execute('SELECT COUNT(*) FROM candles_1m').fetchone()[0]
            conn.close()
            self.assertEqual(n,remaining)
        finally:
            cs.CANDLE_DB_PATH = old
            for suffix in ('','-wal','-shm','-journal'):
                p=path+suffix
                if os.path.exists(p): os.remove(p)


class OneMinuteBacktestTests(unittest.TestCase):
    def test_one_minute_execution_path(self):
        c=[]
        for i in range(3600):
            px=100 + i*0.01
            c.append({'t':i*60,'o':px,'h':px+0.2,'l':px-0.2,'c':px+0.05,'v':1000})
        trades=run_symbol('BTC-USDT', c, max_bars=20)
        self.assertIsInstance(trades, list)


if __name__=='__main__': unittest.main()
