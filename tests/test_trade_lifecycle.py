"""v11.2.0 trade lifecycle tests (restored + expiry guard tests)."""
import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from signal_store import CSV_HEADERS, append_signal_row, load_open_signals, resolve_signal, should_expire, signal_age_hours


class TradeLifecycleTests(unittest.TestCase):
    def test_margin_leverage_and_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            with patch('signal_store.SIGNALS_DIR', td):
                path, row = append_signal_row(
                    'BTC-USDT', 'LONG', 'MEDIUM', 100.0, 95.0, 110.0,
                    '2026-09-04 12:00:00', 'test',
                    position_margin_usd=10.0, leverage=10.0,
                    telegram_message_id=123, issued_at_epoch=1000
                )
                self.assertEqual(float(row['notional_usd']), 100.0)
                opens = load_open_signals()
                self.assertEqual(len(opens), 1)
                self.assertEqual(opens[0]['telegram_message_id'], '123')
                self.assertTrue(resolve_signal(opens[0], '2026-09-04 12:10:00', 110.0, 9.8, 0.2, 'TP_HIT', 456))
                self.assertEqual(load_open_signals(), [])
                with open(path, newline='', encoding='utf-8') as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(rows[0]['status'], 'TP_HIT')
                self.assertEqual(rows[0]['resolution_message_id'], '456')

    def test_header_is_stable(self):
        self.assertIn('telegram_message_id', CSV_HEADERS)
        self.assertIn('resolution_message_id', CSV_HEADERS)
        self.assertIn('position_margin_usd', CSV_HEADERS)
        self.assertIn('leverage', CSV_HEADERS)
        self.assertIn('notional_usd', CSV_HEADERS)


class ExpiryGuardTests(unittest.TestCase):
    def test_should_expire_by_age(self):
        now = 10_000_000
        fresh = {'status': 'OPEN', 'issued_at_epoch': str(now - 3600)}       # 1h old
        stale = {'status': 'OPEN', 'issued_at_epoch': str(now - 400_000)}    # ~111h old
        resolved = {'status': 'TP_HIT', 'issued_at_epoch': str(now - 400_000)}
        self.assertFalse(should_expire(fresh, now, 96))
        self.assertTrue(should_expire(stale, now, 96))
        self.assertFalse(should_expire(resolved, now, 96))
        # disabled (0) never expires
        self.assertFalse(should_expire(stale, now, 0))
        self.assertAlmostEqual(signal_age_hours(stale, now), 400_000/3600.0, places=6)

    def test_resolved_row_never_reopens_via_expiry(self):
        with tempfile.TemporaryDirectory() as td:
            with patch('signal_store.SIGNALS_DIR', td):
                append_signal_row('ETH-USDT', 'SHORT', 'MEDIUM', 2000.0, 2040.0, 1900.0,
                                  '2026-10-01 10:00:00', 'test',
                                  telegram_message_id=9, issued_at_epoch=10_000)
                opens = load_open_signals()
                self.assertEqual(len(opens), 1)
                self.assertTrue(resolve_signal(opens[0], '2026-10-01 11:00:00', 2040.0,
                                               -9.5, 0.4, 'STOP_HIT', 555))
                # ledger must be fully resolved and expiry must not touch it
                self.assertEqual(load_open_signals(), [])
                with open(opens[0]['_path'], newline='', encoding='utf-8') as f:
                    rows = list(csv.DictReader(f))
                self.assertEqual(rows[0]['status'], 'STOP_HIT')
                self.assertFalse(should_expire(rows[0], 10_000 + 500_000, 96))


class OneMinuteResolutionTests(unittest.TestCase):
    def test_first_hit_uses_new_1m_candles_and_conservative_tie(self):
        from bot import _resolve_from_1m
        row = {
            'symbol': 'BTC-USDT', 'direction': 'LONG', 'entry_price': '100',
            'stop_loss': '95', 'take_profit': '105', 'issued_at_epoch': '1000',
            'last_checked_epoch': '1000', 'notional_usd': '100'
        }
        candles = [
            {'t': 1060, 'o': 100, 'h': 103, 'l': 99, 'c': 102, 'v': 1},
            {'t': 1120, 'o': 102, 'h': 106, 'l': 94, 'c': 100, 'v': 1},
        ]
        outcome, exit_price, pnl, fee, hit_epoch, checkpoint = _resolve_from_1m(row, candles)
        self.assertEqual(outcome, 'STOP_HIT')
        self.assertEqual(hit_epoch, 1120)
        self.assertEqual(checkpoint, 1120)
        self.assertLess(pnl, 0)

    def test_checkpoint_only_advances_when_no_hit(self):
        from bot import _resolve_from_1m
        row = {
            'symbol': 'BTC-USDT', 'direction': 'SHORT', 'entry_price': '100',
            'stop_loss': '105', 'take_profit': '95', 'issued_at_epoch': '1000',
            'last_checked_epoch': '1000', 'notional_usd': '100'
        }
        candles = [{'t': 1060, 'o': 100, 'h': 102, 'l': 98, 'c': 99, 'v': 1}]
        outcome, *_rest, checkpoint = _resolve_from_1m(row, candles)
        self.assertIsNone(outcome)
        self.assertEqual(checkpoint, 1060)


class TelegramUITests(unittest.TestCase):
    def test_signal_message_shows_sl_distance(self):
        from telegram_ui import signal_message
        result = {'symbol': 'BTC-USDT', 'direction': 'LONG', 'price': 100.0,
                  'stop_loss': 97.0, 'take_profit': 106.3, 'rr': 2.1,
                  'rule_score': 61.0, 'confidence': 63.0, 'components': []}
        msg = signal_message(result, '11.2.0', 10.0, 10)
        self.assertIn('فاصله SL', msg)
        self.assertIn('3.00%', msg)
        self.assertIn('KHOSRO SIGNAL', msg)

    def test_resolution_message_expired_variant(self):
        from telegram_ui import resolution_message
        row = {'symbol': 'XRP-USDT', 'direction': 'LONG', 'entry_price': '0.5'}
        msg = resolution_message(row, 'EXPIRED', 0.51, 1.5, 0.1, 10.0, 10)
        self.assertIn('EXPIRED', msg)
        self.assertIn('انقضای معامله', msg)
        # classic outcomes unchanged
        tp_msg = resolution_message(row, 'TP_HIT', 0.55, 8.0, 0.1, 10.0, 10)
        sl_msg = resolution_message(row, 'STOP_HIT', 0.48, -4.0, 0.1, 10.0, 10)
        self.assertIn('TAKE PROFIT', tp_msg)
        self.assertIn('STOP LOSS', sl_msg)


if __name__ == '__main__':
    unittest.main()
