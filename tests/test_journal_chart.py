"""Run with: python -m unittest discover -s tests -p 'test_*.py'."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import journal_chart as chart


def candle(ts, price=600):
    return {"time": ts, "open": price, "high": price+1, "low": price-1, "close": price}


class JournalChartTests(unittest.TestCase):
    def setUp(self):
        chart._cache.clear()

    def test_historical_month_and_dst(self):
        for day, hour in (("2026-01-15", 14), ("2026-07-15", 13)):
            with patch('alpha_vantage.fetch_intraday', return_value={"bars": [candle(day+' 09:30:00')]}) as fetch:
                result = chart.intraday_bars('spy', day)
                self.assertEqual(fetch.call_args.kwargs['month'], day[:7])
                expected = int(datetime.fromisoformat(f'{day}T{hour}:30:00+00:00').timestamp())
                self.assertEqual(result['bars'][0]['time'], expected)
                chart.intraday_bars('SPY', day)
                self.assertEqual(fetch.call_count, 1)

    def test_invalid_requests_do_not_fetch(self):
        with patch('alpha_vantage.fetch_intraday') as fetch:
            for symbol, day, interval in [('SPY','invalid','5min'), ('SPY','2026-01-15','bad'), ('','2026-01-15','5min')]:
                self.assertIn('error', chart.intraday_bars(symbol, day, interval))
            fetch.assert_not_called()

    def test_clean_removes_bad_candles_and_sorts_unique_times(self):
        self.assertEqual([b['time'] for b in chart._clean([candle(2), candle(1), candle(2), candle(3, float('nan'))])], [1,2])

    def test_recent_fallback_after_provider_failure(self):
        day = datetime.now(chart._NY).date() - timedelta(days=1)
        dt = datetime.combine(day, datetime.min.time()).replace(hour=10, tzinfo=chart._NY)
        stamp = SimpleNamespace(tzinfo=chart._NY, tz_convert=lambda tz: dt, timestamp=dt.timestamp)
        frame = SimpleNamespace(iterrows=lambda: [(stamp, {'Open':600,'High':601,'Low':599,'Close':600})])
        ticker = SimpleNamespace(history=lambda **kwargs: frame)
        yf = SimpleNamespace(Ticker=lambda symbol: ticker, set_tz_cache_location=lambda path: None)
        with patch('alpha_vantage.fetch_intraday', side_effect=RuntimeError('plan unavailable')), patch.dict(sys.modules, {'yfinance':yf}):
            result = chart.intraday_bars('SPY', day.isoformat())
        self.assertEqual(result['source'], 'Yahoo Finance')
        self.assertEqual(result['bars'][0]['time'], int(dt.timestamp()))

    def test_old_unavailable_data_is_explicit(self):
        with patch('alpha_vantage.fetch_intraday', side_effect=RuntimeError('plan unavailable')):
            result = chart.intraday_bars('SPY', '2020-01-15')
        self.assertEqual(result['bars'], [])
        self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()
