# KhosroSignalAnalyzerBot

ربات تحلیل تکنیکال چند تایم‌فریمی کریپتوکارنسی که با استفاده از داده‌های زنده KuCoin، سیگنال‌های خرید (لانگ) و فروش (شورت) را در **سه سطح ریسک** صادر می‌کند و مستقیم به تلگرام ارسال می‌کند.

## سطوح ریسک

ربات سه سطح ریسک متفاوت دارد که هر کدام تعادل متفاوتی بین **کیفیت سیگنال** و **تعداد سیگنال** ارائه می‌دهند:

| سطح ریسک       | ایموجی | توضیح                                                                 | تعداد قوانین لازم از ۹ | تخمین Win Rate | تعداد سیگنال تقریبی (در ماه) |
|---------------|--------|-----------------------------------------------------------------------|-------------------------|----------------|--------------------------------|
| **ریسک کم**   | 🟢 🦁  | سیگنال‌های بسیار باکیفیت و مطمئن — فقط در روندهای قوی و همگرایی کامل | ≥ ۷ از ۹                | ۷۵–۸۵٪         | ۱–۳                            |
| **ریسک میانی**| 🟡 🐺  | تعادل عالی بین کیفیت و تعداد — پیشنهاد اصلی برای اکثر تریدرها        | ≥ ۶ از ۹                | ۷۰–۷۸٪         | ۴–۸                            |
| **ریسک بالا** | 🔴 🐒  | حساس‌تر — فرصت‌های بیشتر، شامل ضد‌روند و اصلاحات کوتاه‌مدت            | ≥ ۵ از ۹                | ۶۵–۷۵٪         | ۸–۱۵+                          |

**نکته مهم**: اگر سیگنال ریسک کم صادر شود، سطوح میانی و بالا نادیده گرفته می‌شوند. اگر میانی صادر شود، بالا نادیده گرفته می‌شود. یعنی همیشه بالاترین سطح ممکن ارسال می‌شود.

## قوانین مشترک (۹ قانون اصلی)

1. **روند ۴h** — قیمت نسبت به EMA21/55/200 + ساختار HH/HL یا LH/LL
2. **روند ۱h** — قیمت نسبت به EMA21/55 + ساختار HH/HL یا LH/LL
3. **EMA21 + ساختار در ۳۰m** — پولبک/رالی به EMA21
4. **کندل قوی ۱۵m** — قدرت بدن کندل بالاتر از حد مشخص
5. **ورود + حجم** — شکست یا نزدیکی سطح swing در ۵m با حجم اسپایک
6. **RSI** — همسویی تایم‌فریم‌ها + شدت (overbought/oversold)
7. **MACD** — همسویی + شدت هیستوگرام
8. **عدم واگرایی** — در ۱h و ۴h
9. **حجم اسپایک + کندل قوی در ۱۵m** — تأیید مومنتوم

**تفاوت در سطوح**:
- ریسک کم: سخت‌ترین حد برای هر قانون
- ریسک میانی: حد متوسط
- ریسک بالا: حد آسان‌تر (مثلاً کندل >۰.۳۵، حجم ≥۱.۱×، فقط ۲/۵ RSI یا MACD کافی)

## نمونه خروجی در تلگرام

### نمونه سیگنال ریسک کم (لانگ)
```
🟢 🦁 ریسک کم | لانگ

نماد: BTC
قوانین گذرانده: 8/9
دلایل: روند 4h: بالای EMA21، EMA55، EMA200 + ساختار HH/HL در 5 کندل, روند 1h: بالای EMA21 و EMA55 + ساختار HH/HL, EMA21 + ساختار 30m, کندل قوی 15m = 0.72 (حد > 0.6), ورود + حجم, RSI: 5/5 همسو + 2 خیلی قوی (>70), MACD: 5/5 همسو + 3 شدت قوی, عدم واگرایی در 1h و 4h

ورود: 87000.00
استاپ: 85500.00
تارگت: 90000.00

⏰ 2025-12-16 15:44:30
```

### نمونه سیگنال ریسک بالا (شورت)
```
🔴 🐒 ریسک بالا | شورت

نماد: FIL
قوانین گذرانده: 6/9
دلایل: روند 4h: زیر EMA21 + ساختار LH/LL در 3 کندل, کندل قوی 15m = 0.51 (حد > 0.35), ورود + حجم, RSI: 4/5 همسو + 1 خیلی قوی (<30), MACD: 4/5 همسو + 2 شدت قوی, عدم واگرایی در 1h و 4h

ورود: 5.8200
استاپ: 6.0500
تارگت: 5.3600

⏰ 2025-12-16 15:44:30
```

# KhosroSignalAnalyzerBot

A multi-timeframe technical analysis bot for cryptocurrencies that uses live KuCoin data to generate Long/Short signals in **three risk levels** and sends them directly to Telegram.

## Risk Levels

The bot has three different risk levels, each offering a different balance between **signal quality** and **signal frequency**:

| Risk Level     | Emoji | Description                                                           | Required Rules (out of 9) | Estimated Win Rate | Approx. Signals per Month |
|----------------|-------|-----------------------------------------------------------------------|---------------------------|--------------------|-----------------------------------|
| **Low Risk**   | 🟢 🦁 | Very high-quality signals — only in strong trends with full confluence | ≥ 7 out of 9              | 75–85%             | 1–3                               |
| **Medium Risk**| 🟡 🐺 | Excellent balance — recommended for most traders                      | ≥ 6 out of 9              | 70–78%             | 4–8                               |
| **High Risk**  | 🔴 🐒 | More sensitive — captures more opportunities including counter-trend  | ≥ 5 out of 9              | 65–75%             | 8–15+                             |

**Important**: If a Low Risk signal is triggered, Medium and High are ignored. If Medium is triggered, High is ignored. Only the highest possible level is sent.

## Common Rules (9 Main Rules)

1. **4h Trend** — Price relative to EMA21/55/200 + HH/HL or LH/LL structure
2. **1h Trend** — Price relative to EMA21/55 + HH/HL or LH/LL structure
3. **EMA21 + Structure in 30m** — Pullback/rally to EMA21
4. **Strong 15m Candle** — Body strength above threshold
5. **Entry + Volume** — Break or near swing level in 5m with volume spike
6. **RSI** — Timeframe confluence + strength (overbought/oversold)
7. **MACD** — Confluence + histogram strength
8. **No Divergence** — In 1h and 4h
9. **Volume Spike + Strong Candle in 15m** — Momentum confirmation

**Differences by level**:
- Low Risk: Strictest thresholds
- Medium Risk: Moderate thresholds
- High Risk: Looser thresholds (e.g., candle >0.35, volume ≥1.1×, only 2/5 RSI or MACD needed)

## Sample Telegram Output

### Low Risk Long Signal
```
🟢 🦁 Low Risk | Long

Symbol: BTC
Rules Passed: 8/9
Reasons: 4h trend: above EMA21, EMA55, EMA200 + HH/HL structure in 5 candles, 1h trend: above EMA21 and EMA55 + HH/HL structure, EMA21 + structure 30m, strong 15m candle = 0.72 (threshold > 0.6), entry + volume, RSI: 5/5 aligned + 2 very strong (>70), MACD: 5/5 aligned + 3 strong intensity, no divergence in 1h and 4h

Entry: 87000.00
Stop: 85500.00
Target: 90000.00

⏰ 2025-12-16 15:44:30
```

### High Risk Short Signal
```
🔴 🐒 High Risk | Short

Symbol: FIL
Rules Passed: 6/9
Reasons: 4h trend: below EMA21 + LH/LL structure in 3 candles, strong 15m candle = 0.51 (threshold > 0.35), entry + volume, RSI: 4/5 aligned + 1 very strong (<30), MACD: 4/5 aligned + 2 strong intensity, no divergence in 1h and 4h

Entry: 5.8200
Stop: 6.0500
Target: 5.3600

⏰ 2025-12-16 15:44:30
```
