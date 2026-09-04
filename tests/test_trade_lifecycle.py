import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from signal_store import CSV_HEADERS, append_signal_row, load_open_signals, resolve_signal


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


if __name__ == '__main__':
    unittest.main()

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
