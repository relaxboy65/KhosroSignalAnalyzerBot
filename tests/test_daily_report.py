import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from signal_store import load_signals_for_date, tehran_date_str
from telegram_ui import daily_report_message


def _row(symbol, direction, status, pnl, fee="0.10", issued="2026-09-19 10:00:00"):
    return {
        "symbol": symbol,
        "direction": direction,
        "status": status,
        "final_pnl_usd": pnl,
        "broker_fee_usd": fee,
        "issued_at_tehran": issued,
        "entry_price": "100",
    }


class DailyReportMessageTests(unittest.TestCase):
    def test_mixed_day_numbers_are_correct(self):
        rows = [
            _row("BTC-USDT", "LONG", "TP_HIT", "9.80"),
            _row("SOL-USDT", "LONG", "TP_HIT", "4.80"),
            _row("XRP-USDT", "SHORT", "STOP_HIT", "-1.20"),
            _row("POL-USDT", "SHORT", "STOP_HIT", "-6.80"),
            _row("ETH-USDT", "LONG", "OPEN", ""),
        ]
        msg = daily_report_message("2026-09-19", rows)
        self.assertIn("2026-09-19", msg)
        self.assertIn("<b>5</b> عدد", msg)
        self.assertIn("🏆 تیک‌پروفت: <b>2</b>", msg)
        self.assertIn("🛑 حد ضرر: <b>2</b>", msg)
        self.assertIn("⏳ هنوز باز: <b>1</b>", msg)
        self.assertIn("50.0%", msg)  # 2 TP of 4 closed
        self.assertIn("+$6.60", msg)  # 9.80+4.80-1.20-6.80
        self.assertIn("⭐ بهترین: BTC-USDT LONG", msg)  # +9.80 > +4.80
        self.assertIn("💀 بدترین: POL-USDT SHORT", msg)

    def test_empty_day_returns_none(self):
        self.assertIsNone(daily_report_message("2026-09-19", []))

    def test_empty_day_with_older_open_still_reports(self):
        msg = daily_report_message("2026-09-19", [], older_open_count=2)
        self.assertIsNotNone(msg)
        self.assertIn("باز از روزهای قبل: <b>2</b>", msg)

    def test_all_open_day_has_no_winrate_line(self):
        msg = daily_report_message("2026-09-19", [_row("BTC-USDT", "LONG", "OPEN", "")])
        self.assertNotIn("نرخ برد", msg)
        self.assertIn("+$0.00", msg)

    def test_html_escaping_of_symbols(self):
        rows = [_row("EVIL<svg>", "LONG", "TP_HIT", "1.0")]
        msg = daily_report_message("2026-09-19", rows)
        self.assertNotIn("EVIL<svg>", msg)
        self.assertIn("EVIL&lt;svg&gt;", msg)


class LoadSignalsForDateTests(unittest.TestCase):
    def test_reads_only_requested_day(self):
        with tempfile.TemporaryDirectory() as td:
            headers = ["symbol", "status", "final_pnl_usd"]
            with open(os.path.join(td, "2026-09-18.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                w.writerow({"symbol": "BTC-USDT", "status": "TP_HIT", "final_pnl_usd": "1.0"})
            with open(os.path.join(td, "2026-09-19.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=headers)
                w.writeheader()
                w.writerow({"symbol": "ETH-USDT", "status": "OPEN", "final_pnl_usd": ""})
            with patch("signal_store.SIGNALS_DIR", td):
                rows18 = load_signals_for_date("2026-09-18")
                rows19 = load_signals_for_date("2026-09-19")
                rows20 = load_signals_for_date("2026-09-20")
            self.assertEqual(len(rows18), 1)
            self.assertEqual(rows18[0]["symbol"], "BTC-USDT")
            self.assertEqual(len(rows19), 1)
            self.assertEqual(rows19[0]["status"], "OPEN")
            self.assertEqual(rows20, [])

    def test_missing_dir_is_empty(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("signal_store.SIGNALS_DIR", os.path.join(td, "nope")):
                self.assertEqual(load_signals_for_date("2026-09-01"), [])

    def test_tehran_date_str_format(self):
        value = tehran_date_str()
        self.assertEqual(len(value), 10)
        self.assertEqual(value[4], "-")
        self.assertEqual(value[7], "-")


if __name__ == "__main__":
    unittest.main()
