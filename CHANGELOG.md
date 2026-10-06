## v11.3.0 — گزارش روزانه تلگرام (ادغام دو شاخه)
- **گزارش روزانه روز قبل (قابلیت جدید):** هر شب بعد از resolve شدن معاملات OPEN، ربات خلاصه عملکرد روز قبل تهران را به تلگرام می‌فرستد: تعداد سیگنال‌ها، تیک‌پروفت/حد ضرر/باز، نرخ برد معاملات بسته‌شده، PnL خالص و کارمزد، تفکیک لانگ/شورت، بهترین و بدترین معامله و تعداد معاملات بازِ روزهای قبل. ماژول جدید `daily_report.py` + `daily_report_message` در `telegram_ui.py` + `load_signals_for_date` در `signal_store.py` + استپ «Send previous-day Telegram report» در `nightly.yml`.
- **گزارش روز قبل قبل از پاک‌سازی:** استپ گزارش قبل از prune CSVها اجرا می‌شود؛ روز بدون سیگنال و بدون معامله باز، پیامی نمی‌فرستد (اسپم صفر).
- **اجراهای دستی:** `python daily_report.py --print` (چاپ بدون ارسال) و `python daily_report.py --date 2026-09-19` (روز مشخص).
- **تست‌های جدید:** ۸ تست گزارش روزانه (درستی اعداد روز مختلط، روز خالی، روز بدون معامله بسته، escape شدن HTML نماد، خواندن CSV روز دقیق، مسیر ناموجود، فرمت تاریخ تهران) — مجموع تست‌ها به ۳۳ عدد رسید.
- این نسخه ادغام کامل v11.2.0 (سقف استاپ، گیت شورت، گارد دیتابیس، concurrency، انقضای ۹۶ ساعته) با قابلیت گزارش روزانه است.

## v11.2.0 — نسخه تمیز و سالم‌سازی‌شده
- **سقف سخت استاپ (فیکس بحرانی):** استاپ ساختاری دیگر هرگز جایگزین استاپ ATR بدون سقف نمی‌شود. فاصله نهایی استاپ در بازه [۰.۵٪، min(۳٪، ۲.۵×ATR)] clamp می‌شود و TP از فاصله نهایی بازمحاسبه می‌شود (R:R ثابت). بدترین ضرر SL با اهرم 10x از -۱۱۰٪ (واقعی در ledger) به -۳۰٪ محدود شد. شرط همیشه-درستِ گیت LONG قدیمی حذف و منطق برای SHORT قرینه شد.
- **گیت سخت‌گیرانه شورت:** روند 4h و 1h برای SHORT باید ≥۰.۶۰ باشد (لانگ ۰.۳۵) + آستانه امتیاز نهایی SHORT برابر ۷۲ (لانگ ۶۲) + قانون ۶ پرامپت AI (شورت فقط با order flow و volume profile نزولی صریح).
- **رفع بحران حجم دیتابیس:** `CANDLE_RETENTION_DAYS` از ۹۰ به ۱۲ کاهش یافت (پوشش کامل lookback ۱۰ روزه resolver)؛ VACUUM بعد از هر prune اضافه شد (SQLite فضای حذف‌شده را بدون آن پس نمی‌دهد)؛ گارد سخت `enforce_db_size_limit` با prune اضطراری ۵ روزه در عبور از ۸۰MB؛ db در ۹۵.۷MB بعد از اولین اجرا به ~۴۵MB می‌رسد.
- **concurrency:** هر ۴ workflow در گروه `khosro-state` قرار گرفتند تا کامیت هم‌زمان و متناقض db/CSV بین signal-bot و collect-1m ممکن نباشد؛ collect به دقیقه ۱۵/۴۵ منتقل شد.
- **انقضای سیگنال کهنه:** سیگنال‌های OPEN بعد از ۹۶ ساعت با وضعیت `EXPIRED` و پیام تلگرام بسته می‌شوند تا نماد برای همیشه قفل نشود (قابل خاموش کردن با `SIGNAL_MAX_AGE_HOURS=0`).
- **بازگشت `tests/`** (در v11.1.1 حذف شده بود) + ۱۲ تست جدید: سقف‌های استاپ، حفظ R:R، گیت شورت، انقضا، VACUUM/گارد حجم، پیام EXPIRED و فاصله SL در تلگرام.
- **بهداشت کد:** تابع مرده `generate_signal` و ثابت استفاده‌نشده `COOLDOWN_BARS` حذف شدند؛ docstring کمیته AI نسخه‌محور و دقیق شد؛ README کامل بازنویسی شد.
- **شفافیت:** `stop_pct` و `stop_capped` و `score_threshold` در خروجی analyze_market؛ نمایش «فاصله SL ٪» در پیام سیگنال تلگرام.

## v11.1.1
- Fixed AI model IDs after live API errors: Groq `openai/gpt-oss-20b`, Cerebras `llama3.1-8b`, Cloudflare `@cf/meta/llama-3.1-8b-instruct-fast` (+ fallbacks).
- SambaNova/SiliconFlow still need account balance (HTTP 402); they fail gracefully.

## v11.1.0
- AI committee expanded to 7 providers: OpenRouter, Mistral, Cerebras, Groq, SambaNova, SiliconFlow, Cloudflare Workers AI.
- Per-provider vote logging (`AI_VOTE` / `AI_COMMITTEE`) and Telegram section listing each API decision, confidence, model, reason.
- Budget is not consumed when no API keys are present.
- Secrets: `GROQ_API_KEY`, `SAMBANOVA_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.

## v11.0.1
- Fixed `generate_signal` calling missing `_analyze_with_ai` (now `analyze_with_ai`).
- Daily signal quota no longer increments on failed checks; `record_signal_issued()` after real issue.
- Live `bot.process_symbol` respects Tehran forbidden hours (00–04) and daily signal limit.
- Telegram signal/result messages: removed disclaimer warning line; version tag shown clearly.
- README + workflows tagged **v11.0.1**. AI committee docs aligned to 4 providers.

## v11.0.0
- **کمیته هوش مصنوعی (AI Committee)** با ۴ سرویس رایگان و رأی وزن‌دهی اضافه شد: OpenRouter (وزن ۳۵)، Mistral (وزن ۳۰)، Cerebras (وزن ۲۵)، SiliconFlow (وزن ۱۰). ماژول جدید `ai_committee.py`.
- **موتور وزن‌دهی جدید v11** طبق اولویت کاربر: AI (25) > Order Flow (14) > Volume Profile (11) > Sweep (10) > Liquidity (8) > FVG (7) > Fibonacci (6) > Supply/Demand (5) > Moving Average (5) > MACD (4) > RSI (3) > Pattern (2). ماژول جدید `smc.py`.
- روند 4h/1h و نوسان ATR از مؤلفه‌های وزن‌دار به **گیت‌های سخت** تبدیل شدند.
- جریان دو-فازی: پیش‌امتیاز قوانین (rule_score) → فقط کاندیدهای بالای ۶۰ به کمیته AI می‌روند → رأی وزن‌دهی → بازمحاسبه امتیاز نهایی. رأی منفی اکثریت AI سیگنال را وتو می‌کند.
- بودجه‌گذاری AI: حداکثر ۶ فراخوانی در هر اجرا و ۴۰ در روز (شمارنده روزانه در `signals/ai_budget_*.json`).
- کلیدهای جدید Secrets: `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `SILICONFLOW_API_KEY` (در workflow اضافه شد).
- `analyze_market` سازگار با backtest ماند (ai_verdict=None → AI خنثی ۰.۵).
- signal_score از ۶۴ به ۶۲ تغییر کرد (به‌دلیل وزن ۲۵ تایی AI و خنثی بودن آن در نبود رأی).

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
