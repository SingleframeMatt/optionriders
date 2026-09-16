"""Deterministic screening checks; these are not return or win-rate backtests."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# A path override allows checking a staged version before installing it.
import os
spec = importlib.util.spec_from_file_location('screening_engine', os.environ.get('TOP_TRADE_TEST_SOURCE', ROOT / 'top_trade_today.py'))
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)
NOW = datetime(2026, 9, 16, 11, 0, tzinfo=engine.NY_TZ)


def bars(count=30, start=None, step=120):
    start = start or NOW - timedelta(seconds=count*step)
    closes = [100 + i*.1 for i in range(count)]
    return {'time':[int(start.timestamp())+i*step for i in range(count)],
            'open':closes, 'close':closes, 'high':[n+.2 for n in closes],
            'low':[n-.2 for n in closes], 'volume':[100]*count}


def quote(bid=1, ask=1.05, side='Call'):
    return {'bid':f'${bid:.2f}', 'ask':f'${ask:.2f}', 'contract':f'105 {side}', 'expirationDate':'2026-09-18'}


def item():
    return {'ticker':'SPY','price':103,'signalScore':60,'relStrength':2,'atrPct':2,
            '_expectedMovePct':2,'bias':'Bullish','support':[99,98], 'resistance':[105,108,110],
            'bullTrigger':'Break above 105','bearTrigger':'Lose 99'}


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        engine._cache.update(payload=None, expires_at=0, session_key=None)

    def score(self, candidate, option_row):
        tf = {k:engine.TimeframeSnapshot(k,'bullish' if candidate['signalScore']>0 else 'bearish',1,1,True,True) for k in ('4h','1h','15m','2m')}
        return engine._score_candidate('SPY',candidate,option_row,None,[],tf,{'choppy':False},None,False)

    def test_selected_option_side_and_percentage(self):
        candidate=item();candidate.update(signalScore=-60,relStrength=-2,bias='Bearish')
        self.assertIsNone(self.score(candidate, {'call':quote(), 'put':quote(0.05,0.1,'Put')}))
        scored=self.score(candidate, {'call':quote(1,2), 'put':quote(2,2.05,'Put')})
        self.assertEqual(scored['direction'],'Put');self.assertAlmostEqual(scored['spread'],.05)
        self.assertNotIn('confidence',scored)
        self.assertIsNone(engine._option_quote({'call':quote(0,0.1)},'Call'))
        self.assertIsNone(engine._option_quote({'call':quote(2,1)},'Call'))

    def test_targets_are_beyond_entry_in_both_directions(self):
        levels=engine._trade_levels(item(),'Call')
        self.assertEqual(levels['targets'],[108,110]);self.assertEqual(levels['stop'],99)
        levels=engine._trade_levels(item(),'Put')
        self.assertEqual(levels['targets'],[98]);self.assertEqual(levels['stop'],105)
        bad=item();bad['resistance']=[105]
        self.assertIsNone(engine._trade_levels(bad,'Call'))
        bad['resistance']=[];self.assertIsNone(engine._trade_levels(bad,'Call'))

    def test_bars_are_aligned_and_forming_bar_is_removed(self):
        times=pd.date_range('2026-09-16 10:54',periods=4,freq='2min',tz=engine.NY_TZ)
        frame=pd.DataFrame({'Open':[100]*4,'High':[101]*4,'Low':[99]*4,'Close':[100, float('nan'),100,100],'Volume':[10]*4},index=times)
        result=engine._frame_bars(frame,NOW,2)
        self.assertEqual(result['time'],[int(times[0].timestamp()),int(times[2].timestamp())])
        self.assertTrue(all(len(v)==2 for v in result.values()))
        self.assertEqual(engine._frame_bars(frame.tz_localize(None),NOW,2)['time'],[])

    def test_intraday_age_and_date(self):
        self.assertTrue(engine._fresh_intraday(bars(),NOW))
        old=bars(start=NOW-timedelta(days=1));self.assertFalse(engine._fresh_intraday(old,NOW))
        forming=bars(start=NOW-timedelta(minutes=58));self.assertFalse(engine._fresh_intraday(forming,NOW))
        self.assertFalse(engine._fresh_intraday(bars(5),NOW))
        fifteen=bars(step=900)
        self.assertTrue(engine._fresh_intraday(fifteen,NOW+timedelta(minutes=14),15))
        self.assertFalse(engine._fresh_intraday(fifteen,NOW+timedelta(minutes=22),15))

    def test_four_hour_blocks_never_cross_session_or_missing_hour(self):
        hourly=bars(8,start=NOW.replace(hour=9,minute=30),step=3600)
        result=engine._collapse_to_4h(hourly)
        self.assertEqual(len(result['time']),1)
        hourly['time'][2]+=3600
        self.assertEqual(engine._collapse_to_4h(hourly)['time'],[])
        self.assertEqual(engine._collapse_to_4h({'close':[1]*20})['time'],[])

    def test_missing_premarket_is_rejected(self):
        tf={k:engine.TimeframeSnapshot(k,'bullish',1,1,True,True) for k in ('4h','1h','15m','2m')}
        self.assertIsNone(engine._score_candidate('SPY',item(),{'call':quote()},None,[],tf,{},None,True))

    def fetch(self, intraday=None, market=None, flow=None):
        with patch.object(engine,'_now_ny',return_value=NOW), \
             patch.object(engine,'fetch_market_data',return_value=market or {'tickers':[item()], 'updatedAt':int(NOW.timestamp())}), \
             patch.object(engine,'fetch_options_activity',return_value=flow if flow is not None else {'updatedAt':int(NOW.timestamp()),'atmSpreads':[{'ticker':'SPY','call':quote(),'put':quote(side='Put')}]}), \
             patch.object(engine,'fetch_top_watch',return_value={}), \
             patch.object(engine,'_fetch_macro_events',return_value={'today':[],'next':[]}), \
             patch.object(engine,'_download_multiframe',return_value=intraday or {'SPY':{'2m':bars(),'15m':bars(step=900)}}), \
             patch.object(engine,'fetch_premarket',return_value={}):
            return engine.fetch_top_trade_today(True)

    def test_end_to_end_real_contract_no_padding(self):
        result=self.fetch()
        self.assertEqual(len(result['picks']),1)
        pick=result['picks'][0]
        self.assertEqual(pick['bestContractIdea'],{'strike':'105 Call','expiry':'2026-09-18'})
        self.assertEqual(pick['profitTargets'],[108,110])
        self.assertNotIn('confidence',pick);self.assertNotIn('riskLevel',pick)
        self.assertEqual(pick['barAsOf'],bars()['time'][-1])

    def test_no_fallback_when_data_missing_or_stale(self):
        result=self.fetch(intraday={'SPY':{}})
        self.assertEqual(result['picks'],[]);self.assertFalse(result['liveData'])
        self.assertEqual(result['excluded']['staleBars'],1)
        self.assertEqual(self.fetch(flow={})['picks'],[])
        stale={'tickers':[item()],'updatedAt':int(NOW.timestamp())-3600}
        self.assertEqual(self.fetch(market=stale)['picks'],[])

    def test_expired_quote_and_stale_fifteen_minute_data(self):
        expired=quote();expired['expirationDate']='2026-09-15'
        result=self.fetch(flow={'updatedAt':int(NOW.timestamp()), 'atmSpreads':[{'ticker':'SPY','call':expired}]})
        self.assertEqual(result['picks'],[])
        self.assertEqual(result['excluded']['expiredContract'],1)
        result=self.fetch(intraday={'SPY':{'2m':bars(),'15m':bars(start=NOW-timedelta(days=1),step=900)}})
        self.assertEqual(result['picks'],[])
        self.assertEqual(result['excluded']['staleBars'],1)

    def test_nan_score_is_rejected_and_comma_trigger_parses(self):
        bad=item();bad['relStrength']=float('nan')
        self.assertIsNone(self.score(bad,{'call':quote()}))
        self.assertEqual(engine._parse_trigger_number('Break above $1,234.56'),1234.56)

    def test_holidays_early_close_and_unknown_calendar(self):
        self.assertEqual(engine._market_session_label(NOW.replace(month=12,day=25)), 'Market closed')
        self.assertEqual(engine._market_session_label(NOW.replace(month=11,day=27,hour=13)), 'Post-close')
        self.assertEqual(engine._market_session_label(NOW.replace(month=11,day=27,hour=12)), 'Regular session')
        self.assertEqual(engine._market_session_label(NOW.replace(year=2029)), 'Calendar unavailable')
        # No substitute New Year holiday on Friday 2027-12-31.
        self.assertEqual(engine._market_session_label(NOW.replace(year=2027,month=12,day=31)), 'Regular session')

    def test_closed_window_avoids_network(self):
        for when in (NOW.replace(hour=16),NOW.replace(hour=3),NOW+timedelta(days=3)):
            with patch.object(engine,'_now_ny',return_value=when),patch.object(engine,'fetch_market_data') as fetch:
                self.assertEqual(engine.fetch_top_trade_today(True)['picks'],[])
                fetch.assert_not_called()


if __name__=='__main__':unittest.main()
