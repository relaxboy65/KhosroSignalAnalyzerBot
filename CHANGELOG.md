## v10.3.0
- Added a dedicated continuous 1m market-data collector process (`collect_1m_data.py --loop`).
- Default collector interval is 120 seconds; minimum allowed interval is 60 seconds.
- Collector is independent from signal generation/trade resolution and continuously maintains the rolling 90-day SQLite cache.
- Added `run_collector.sh` launcher and a systemd service example for production deployment.

## v10.2.0
- Added SQLite `market_data.db` for 1-minute OHLCV storage.
- Rolling retention is 90 days with automatic pruning.
- Live bot incrementally syncs 1m candles and resolves OPEN trades from the local database.
- Added `collect_1m_data.py` for initial/full 90-day history collection.
- Backtest can replay 1m database candles while keeping strategy decisions on 5m/15m/30m/1h/4h data.

# Changelog

## 10.1.0 — 2026-09-04

- نتیجه معاملات از 5m به **1m بسته‌شده** ارتقا یافت.
- دریافت کندل 1m به‌صورت pagination انجام می‌شود.
- `last_checked_epoch` برای جلوگیری از اسکن تکراری داده‌های قدیمی اضافه شد.
- در خطای دریافت دیتا، checkpoint جلو نمی‌رود تا نتیجه‌ای از دست نرود.
- اگر ارسال پیام نتیجه به Telegram شکست بخورد، معامله OPEN باقی می‌ماند تا اجرای بعدی دوباره تلاش کند.
- ارسال Telegram با lock، فاصله حداقل 3.2 ثانیه و پشتیبانی از `retry_after` برای 429 ایمن شد؛ فاصله 3.2 ثانیه برای رعایت سقف 20 پیام در دقیقه در گروه‌ها نیز محافظه‌کارانه است.
- پیام‌های سیگنال و نتیجه فاخرتر شدند و نتیجه همچنان Reply به پیام اصلی است.
- `monitor_nightly.py` به entry point سازگار برای موتور واحد `bot.py` تبدیل شد تا دو موتور lifecycle متفاوت هم‌زمان وجود نداشته باشند.
- تست‌های lifecycle برای 1m و رفتار STOP-first اضافه شد.

## 10.0.0 — 2026-09-04

### Added
- Fixed trade model: $10 margin with 10x leverage = $100 notional per signal.
- Persistent OPEN signal lifecycle across daily CSV files.
- Automatic resolution of previous OPEN signals on every bot execution.
- TP/SL resolution from closed 5m candles after signal timestamp.
- Conservative STOP-first handling when TP and SL are both touched in one candle.
- Net PnL calculation on notional with round-trip fees.
- Telegram signal message IDs stored in the ledger.
- Resolution messages sent as Telegram replies to the original signal message.
- New premium Telegram HTML message layout.
- Per-symbol protection against stacking a new signal while an older one is OPEN.
- `reset_signals.py` for creating a clean daily ledger.
- Lifecycle unit tests.

### Changed
- Signal ledger schema expanded with timestamp, margin, leverage, notional and Telegram message IDs.
- Version bumped from 9.0.0 to 10.0.0 because the trade lifecycle contract changed.
- Historical signal CSV files removed; project starts from a clean 2026-09-04 ledger.

### Fixed
- Corrected the SHORT TP/SL handling already introduced in v9 and carried forward into the live lifecycle resolver.
