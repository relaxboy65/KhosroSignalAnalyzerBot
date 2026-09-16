# KhosroSignalAnalyzerBot — v11.0.1

**Khosro Confluence Engine + AI Committee** — موتور سیگنال‌دهی چندتایم‌فریمی کریپتو با ۱۰ مؤلفه SMC/تکنیکال و **کمیته وزن‌دهی ۴ سرویس هوش مصنوعی رایگان** (OpenRouter / Mistral / Cerebras / SiliconFlow).

> ⚠️ این پروژه ابزار تحلیل و بک‌تست است و سود یا دقت تضمین‌شده ندارد. اهرم ریسک را چند برابر می‌کند. قبل از استفاده واقعی، Paper Trading و کنترل ریسک مستقل انجام دهید.

## تغییر اصلی v10

از این نسخه، هر سیگنال یک معامله فرضی با مدل ثابت زیر است:

- سرمایه/مارجین هر سیگنال: **$10**
- اهرم: **10x**
- حجم اسمی معامله: **$100**
- کارمزد رفت و برگشت: بر اساس `BROKER_FEE_RATE` و حجم اسمی
- PnL روی حجم اسمی $100 محاسبه می‌شود و سپس کارمزد کسر می‌گردد.

### چرخه عمر سیگنال

```text
NEW SIGNAL
    ↓
Telegram message
    ↓
message_id saved in CSV
    ↓
OPEN
    ↓
هر اجرای بعدی ربات
    ↓
بررسی **1m candles** بعد از زمان سیگنال
    ↓
TP یا SL ؟
    ├── TP → محاسبه PnL → پیام جدید Reply به پیام اصلی
    └── SL → محاسبه PnL → پیام جدید Reply به پیام اصلی
```

اگر یک کندل هم‌زمان هم SL و هم TP را لمس کند، ترتیب واقعی intrabar از OHLC قابل تشخیص نیست؛ سیستم محافظه‌کارانه **STOP first** را انتخاب می‌کند.

تا زمانی که سیگنال یک نماد OPEN است، ربات برای همان نماد سیگنال جدید صادر نمی‌کند تا معاملات روی یک دارایی روی هم انباشته نشوند.

## پیام‌های تلگرام

پیام سیگنال با HTML Telegram API، بخش‌بندی واضح، **نسخه ربات (v11.0.1)**، Confidence، Entry/SL/TP، R:R، سرمایه، اهرم، حجم اسمی و مهم‌ترین عوامل ساخته می‌شود (بدون متن هشدار تکراری).

پس از بسته‌شدن معامله، پیام نتیجه **به‌صورت Reply مستقیم به پیام اصلی همان سیگنال** ارسال می‌شود. `telegram_message_id` در ledger نگهداری می‌شود.

اگر پیام اصلی به هر دلیل Message ID نداشته باشد، نتیجه همچنان ارسال می‌شود اما Reply مستقیم ممکن نیست.

## Ledger و داده‌های سیگنال

فایل‌های قدیمی نسخه‌های قبلی پاک شده‌اند و پروژه از امروز با این فایل شروع می‌شود:

```text
signals/2026-09-04.csv
```

فایل در شروع خالی است و فقط header دارد. از این به بعد هر روز ledger جداگانه ساخته می‌شود و سیگنال‌های OPEN روزهای قبل نیز قابل پیگیری هستند.

ستون‌های مهم:

- `status`
- `issued_at_epoch`
- `position_margin_usd`
- `leverage`
- `notional_usd`
- `final_pnl_usd`
- `broker_fee_usd`
- `telegram_message_id`
- `resolution_message_id`

## موتور سیگنال (v11)

```text
Market Data (5m/15m/30m/1h/4h)
   ↓
گیت روند HTF  (4h + 1h باید هم‌جهت باشند — بدون وزن، فقط فیلتر)
   ↓
گیت نوسان  (ATR% ≤ حد مجاز — بدون وزن، فقط فیلتر)
   ↓
۱۰ مؤلفه وزن‌دار SMC/تکنیکال (order flow, volume profile, sweep, ...)
   ↓
پیش‌امتیاز قوانین (rule_score ۰ تا ۱۰۰)
   ↓
rule_score ≥ 60 ؟ ─── خیر ──→ NO SIGNAL (صرفه‌جویی در سهمیه AI)
   ↓ بله
کمیته AI (۳ سرویس رایگان، رأی وزن‌دهی)
   ↓
امتیاز نهایی وزن‌دهی ۰–۱۰۰ (وزن AI = ۲۵، بزرگ‌ترین وزن)
   ↓
SIGNAL / NO SIGNAL (رأی منفی AI سیگنال را وتو می‌کند)
   ↓
Entry / SL / TP / R:R
```

## مدل امتیازدهی (v11)

| رتبه | مؤلفه | وزن |
|---:|---|---:|
| ۱ | **کمیته هوش مصنوعی (۳ سرویس رایگان)** | **25** |
| ۲ | Order Flow (اوردر فلو) | 14 |
| ۳ | Volume Profile (POC + Value Area) | 11 |
| ۴ | Sweep (سوییپ لیکوییدیتی) | 10 |
| ۵ | Liquidity Pools (سطوح برابر بالا/پایین) | 8 |
| ۶ | FVG (Fair Value Gap غیرمیتگیت‌شده) | 7 |
| ۷ | Fibonacci (زون طلایی اصلاح) | 6 |
| ۸ | Supply / Demand Zones | 5 |
| ۹ | Moving Average (EMA21/50 + شیب) | 5 |
| ۱۰ | MACD | 4 |
| ۱۱ | RSI | 3 |
| ۱۲ | الگوهای کندلی | 2 |
| | **مجموع** | **100** |

- روند 4h/1h و نوسان ATR دیگر وزن ندارند؛ به‌عنوان **گیت سخت** عمل می‌کنند (عدم عبور = NO SIGNAL قطعی).
- `rule_score` = امتیاز فقط-قوانین (بدون AI) از ۱۰۰؛ فقط کاندیدهای بالای ۶۰ به کمیته AI می‌روند (حفظ سهمیه رایگان).
- رأی هر سرویس AI: approve → `confidence/100`، reject → `((100-confidence)/100)×0.5`.
- رأی منفی اکثریت کمیته، سیگنال را **وتو** می‌کند حتی اگر امتیاز قوانین بالا باشد.

## کمیته هوش مصنوعی

| سرویس | مدل اصلی | وزن رأی | کلید (Environment/Secret) |
|---|---|---:|---|
| OpenRouter | `nvidia/nemotron-3-super-120b-a12b:free` (+۳ مدل جایگزین) | 35 | `OPENROUTER_API_KEY` |
| Mistral | `open-mistral-nemo` | 30 | `MISTRAL_API_KEY` |
| Cerebras | `llama-3.3-70b` | 25 | `CEREBRAS_API_KEY` |
| SiliconFlow | `Qwen/Qwen2.5-7B-Instruct` | 10 | `SILICONFLOW_API_KEY` |

- هر چهار سرویس OpenAI-compatible و رایگان‌اند؛ اگر یک سرویس خطا بدهد (rate-limit/موجودی)، بقیه رأی می‌دهند و کمیته ادامه می‌دهد.
- اگر مدل اصلی OpenRouter موقتاً rate-limit شود، به‌ترتیب روی ۳ مدل رایگان جایگزین تلاش می‌شود.
- خروجی هر رأی JSON سخت‌گیرانه `decision/confidence/reason` است (مدل‌های reasoning هم پشتیبانی می‌شوند).
- بودجه مصرف: حداکثر ۶ فراخوانی در هر اجرا و ۴۰ در روز (`AI_MAX_CALLS_PER_RUN`, `AI_DAILY_BUDGET`).
- اگر هیچ سرویسی در دسترس نباشد، کمیته «غیرفعال» می‌شود و مؤلفه AI خنثی (۰.۵) حساب می‌شود (قطعی شبکه هرگز سیگنال را خودکار تایید یا رد نمی‌کند).
- قوانین معاملاتی شما برای AI از `AI_RULES_TEXT` در `config.py` خوانده می‌شود و داخل پرامپت تزریق می‌گردد.

آستانه‌ها:

- 78+ → LOW
- 68–77.99 → MEDIUM
- 62–67.99 → HIGH
- کمتر از 62 → NO SIGNAL

## مدیریت SL/TP

| Risk | ATR Stop | R:R پایه |
|---|---:|---:|
| LOW | 1.4× ATR | 2.4R |
| MEDIUM | 1.6× ATR | 2.1R |
| HIGH | 1.9× ATR | 2.0R |

## PnL با $10 و اهرم 10x

برای LONG:

```text
Gross PnL = $100 × (Exit - Entry) / Entry
Net PnL = Gross PnL - round_trip_fee
```

برای SHORT:

```text
Gross PnL = $100 × (Entry - Exit) / Entry
Net PnL = Gross PnL - round_trip_fee
```

بنابراین بازده درصدی گزارش‌شده نسبت به **$10 سرمایه/مارجین** است، نه نسبت به $100 حجم اسمی.

مثلاً حرکت 2% در جهت معامله تقریباً $2 سود ناخالص روی حجم $100 ایجاد می‌کند، قبل از کارمزد و slippage.

## اجرای ربات

```bash
python -m pip install -r requirements.txt

# Linux/macOS
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export OPENROUTER_API_KEY="..."    # openrouter.ai
export MISTRAL_API_KEY="..."       # console.mistral.ai
export SILICONFLOW_API_KEY="..."   # cloud.siliconflow.com

python bot.py
```

Windows PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="..."
$env:TELEGRAM_CHAT_ID="..."
$env:OPENROUTER_API_KEY="..."
$env:MISTRAL_API_KEY="..."
$env:SILICONFLOW_API_KEY="..."
python bot.py
```

## رفتار هر اجرای ربات

1. فایل‌های signal را می‌خواند.
2. همه سیگنال‌های `OPEN` را پیدا می‌کند.
3. برای نمادهای دارای معامله باز، فقط داده **1m** برای تعیین دقیق TP/SL می‌گیرد.
4. از اولین کندل بسته‌شده بعد از زمان سیگنال، TP/SL را بررسی می‌کند.
5. در صورت برخورد، PnL واقعی شبیه‌سازی‌شده را محاسبه می‌کند.
6. نتیجه را در یک پیام جدید Reply به پیام اصلی می‌فرستد.
7. CSV را به `TP_HIT` یا `STOP_HIT` تغییر می‌دهد.
8. سپس دوباره ledger را می‌خواند.
9. برای نمادهایی که دیگر OPEN نیستند، اجازه تحلیل سیگنال جدید می‌دهد.

## نکته مهم درباره تشخیص خروج

ربات برای جلوگیری از look-ahead از کندل‌های بسته‌شده استفاده می‌کند. اگر TP و SL در یک کندل لمس شوند، به علت نبود اطلاعات tick-by-tick، **SL اول** در نظر گرفته می‌شود.

## تعیین نتیجه با کندل 1 دقیقه‌ای

سیگنال‌ها همچنان با تایم‌فریم‌های استراتژی (30m/1h/4h و سایر ورودی‌های موتور) ساخته می‌شوند، اما **فقط برای lifecycle معامله** از کندل 1m استفاده می‌شود. این کار زمان برخورد TP/SL را دقیق‌تر می‌کند و از خطای بزرگ‌تر شدن دامنه داخل یک کندل 5m جلوگیری می‌کند.

- فقط کندل‌های 1m بسته‌شده بررسی می‌شوند.
- `last_checked_epoch` در ledger ذخیره می‌شود؛ بنابراین هر اجرای ربات فقط بخش جدید داده را دوباره بررسی می‌کند.
- دریافت 1m صفحه‌بندی شده است و محدودیت 1500 کندل هر درخواست KuCoin را دور می‌زند.
- اگر در یک دقیقه هر دو TP و SL لمس شوند، چون ترتیب intrabar از OHLC مشخص نیست، سیاست محافظه‌کارانه **STOP first** اعمال می‌شود.

## کنترل محدودیت Telegram

Telegram برای یک chat توصیه می‌کند بیشتر از یک پیام در ثانیه ارسال نشود و برای group نیز محدودیت جداگانه دارد. این نسخه ارسال‌ها را در یک صف منطقی سریالی می‌کند، بین پیام‌ها حداقل **1.10 ثانیه** فاصله می‌گذارد و در پاسخ HTTP 429 مقدار `retry_after` را رعایت می‌کند. در نتیجه اگر چند معامله هم‌زمان بسته شوند، پیام‌های نتیجه پشت‌سرهم ولی کنترل‌شده ارسال می‌شوند؛ هیچ نتیجه‌ای عمداً به‌خاطر rate limit حذف نمی‌شود. citeturn0search1turn0search0

## بک‌تست

برای بک‌تست چندماهه واقعی، سیگنال‌سازی همچنان با تایم‌فریم‌های تحلیلی انجام می‌شود؛ برای تعیین نتیجه معامله باید **OHLCV خام 1m** نیز در دسترس باشد:

```bash
python download_backtest_data.py --symbol BTC-USDT --days 180
python backtest.py --symbol BTCUSDT --data-dir backtest_data --out backtest_report.txt
```

برای ETH:

```bash
python download_backtest_data.py --symbol ETH-USDT --days 180
python backtest.py --symbol ETHUSDT --data-dir backtest_data --out eth_report.txt
```

Backtest نیز باید از مدل سرمایه جدید استفاده کند: $10 margin × 10x = $100 notional. نتیجه قبلی پروژه که با داده‌های تاریخی موجود محاسبه شده بود، **baseline نسخه قبلی** است و نتیجه v10 محسوب نمی‌شود.

## تست و کنترل کیفیت

قبل از انتشار نسخه:

```bash
python -m compileall -q .
python -m unittest discover -s tests -v
```

تست‌ها موارد زیر را پوشش می‌دهند:

- Indicatorها
- ADX / DI
- Stochastic K/D
- شکل خروجی Analyzer
- اجرای Backtest
- ساخت ledger جدید
- مدل $10 × 10x
- ذخیره Message ID تلگرام
- resolve کردن OPEN → TP/SL
- ذخیره Resolution Message ID

## تنظیمات مهم

در `config.py`:

```python
MARGIN_USD = 10.0
LEVERAGE = 10.0
NOTIONAL_USD = MARGIN_USD * LEVERAGE
BROKER_FEE_RATE = 0.001
SLIPPAGE_PCT = 0.0005
```

اگر کارمزد صرافی واقعی شما متفاوت است، `BROKER_FEE_RATE` را تغییر دهید.

## محدودیت‌ها

- این پروژه الگوریتم خصوصی UpsideGPT را در اختیار ندارد.
- وزن‌ها و فرمول‌های v10 متعلق به این پروژه هستند.
- OHLCV ترتیب دقیق داخل کندل را نشان نمی‌دهد.
- هزینه funding در این مدل لحاظ نشده است.
- liquidation و maintenance margin صرافی به‌صورت کامل شبیه‌سازی نشده‌اند.
- اهرم 10x به معنی سود 10 برابر تضمین‌شده نیست؛ PnL بر اساس حجم اسمی محاسبه می‌شود و ریسک لیکوییدیشن جداست.

## Version

**11.0.1**

v11.0.1: fix generate_signal name, daily quota, forbidden-hour gate in live bot; Telegram without disclaimer warning; version tag in messages.

v10.1.0 دقت تعیین نتیجه معامله را از 5m به 1m ارتقا می‌دهد و کنترل نرخ ارسال Telegram را اضافه می‌کند.


### 1-minute market database
The bot maintains `market_data.db` (SQLite) as a rolling local cache of 1-minute OHLCV candles. Data older than 90 days is automatically removed.

### Dedicated 1m collector process

For production, run the market-data collector as a **separate process** from the Telegram signal bot. This keeps the 1m data feed alive even when the signal-analysis process is restarted and avoids coupling data collection to signal generation.

Run continuously every 2 minutes (recommended default):

```bash
python collect_1m_data.py --loop --interval 120
```

Or use the launcher:

```bash
./run_collector.sh
```

The collector is incremental: after the initial backfill it requests only missing 1m candles, writes them to SQLite, and prunes data older than 90 days on every cycle. The same `market_data.db` is then available to the live resolver and the 1m backtester.

For Linux/systemd, `khosro-1m-collector.service.example` is included as a deployment template.

For a new installation, the live bot makes a small safety backfill for symbols that have no cached data. To build the full initial 90-day dataset for later backtests, run:

```bash
python collect_1m_data.py --days 90
```

For one symbol:

```bash
python collect_1m_data.py --symbol BTC-USDT --days 90
```

Backtest directly from the SQLite database:

```bash
python backtest.py --db market_data.db --symbol BTC-USDT
```

The live trade resolver and database use closed 1-minute candles; if TP and SL are both touched inside the same 1-minute candle, the conservative SL-first rule is used.
