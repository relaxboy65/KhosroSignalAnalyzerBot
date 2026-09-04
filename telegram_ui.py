from html import escape


def _fmt_price(value):
    value = float(value)
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    return f"{value:.8f}"


def signal_message(result, version, margin, leverage):
    direction = result["direction"]
    long = direction == "LONG"
    icon = "🟢" if long else "🔴"
    side = "LONG · خرید" if long else "SHORT · فروش"
    rr = result.get("rr") or 0
    confidence = float(result.get("confidence", result.get("score", 0)))
    components = result.get("components", [])
    top = sorted(components, key=lambda x: x.get("score", 0), reverse=True)[:4]
    factors = "\n".join(
        f"  ├─ {escape(str(c['name']))}: <b>{float(c['score']):.2f}</b>"
        for c in top
    ) or "  └─ تأییدهای کافی ثبت نشده است"
    return (
        f"<b>╔═ {icon} KHOSRO SIGNAL ═╗</b>\n"
        f"<b>{escape(result['symbol'])}</b>  ·  <b>{side}</b>  ·  <code>v{escape(version)}</code>\n"
        f"╚════════════════════╝\n\n"
        f"🎯 <b>Confidence</b>  <code>{confidence:.1f}%</code>\n\n"
        f"💼 <b>سرمایه:</b> ${margin:.2f}  ×  <b>{leverage:g}x</b>\n"
        f"📦 <b>حجم اسمی:</b> ${margin*leverage:.2f}\n\n"
        f"<b>╭─ نقشه معامله ─╮</b>\n"
        f"  ├─ ورود       <code>{_fmt_price(result['price'])}</code>\n"
        f"  ├─ حد ضرر     <code>{_fmt_price(result['stop_loss'])}</code>\n"
        f"  ├─ هدف        <code>{_fmt_price(result['take_profit'])}</code>\n"
        f"  └─ نسبت R:R   <b>1 : {rr:.2f}</b>\n"
        f"<b>╰────────────────╯</b>\n\n"
        f"<b>🔎 مهم‌ترین تأییدها</b>\n{factors}\n\n"
        f"<i>⏱ نتیجه معامله با کندل‌های 1 دقیقه‌ای پایش می‌شود.</i>\n"
        f"<i>⚠️ سیگنال صرفاً برای تحلیل است و سود تضمین‌شده نیست.</i>"
    )


def resolution_message(row, outcome, hit_price, pnl_usd, fee_usd, margin, leverage):
    win = outcome == "TP_HIT"
    icon = "🏆" if win else "🛑"
    title = "TAKE PROFIT · معامله موفق" if win else "STOP LOSS · معامله بسته شد"
    sign = "+" if pnl_usd >= 0 else ""
    ret = (pnl_usd / margin) * 100 if margin else 0.0
    return (
        f"<b>╔═ {icon} TRADE RESULT ═╗</b>\n"
        f"<b>{escape(row.get('symbol',''))}</b>  ·  <b>{escape(row.get('direction',''))}</b>\n"
        f"╚════════════════════╝\n\n"
        f"↩️ <b>نتیجه سیگنال اصلی</b>\n\n"
        f"📍 Entry  <code>{_fmt_price(row.get('entry_price', 0))}</code>\n"
        f"🏁 Exit   <code>{_fmt_price(hit_price)}</code>\n"
        f"💼 Margin <b>${margin:.2f}</b>  ·  <b>{leverage:g}x</b>\n"
        f"📦 Notional <b>${margin*leverage:.2f}</b>\n\n"
        f"<b>╭─ نتیجه مالی ─╮</b>\n"
        f"  ├─ PnL خالص     <b>{sign}${pnl_usd:.4f}</b>\n"
        f"  ├─ کارمزد        <b>${fee_usd:.4f}</b>\n"
        f"  └─ بازده سرمایه  <b>{sign}{ret:.2f}%</b>\n"
        f"<b>╰────────────────╯</b>\n\n"
        f"<i>محاسبه بر اساس کندل 1 دقیقه‌ای، حجم اسمی معامله و کارمزد رفت‌وبرگشت انجام شده است.</i>"
    )
