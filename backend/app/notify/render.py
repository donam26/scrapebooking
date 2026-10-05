# ruff: noqa: E501  (chuỗi HTML nội tuyến dễ đọc hơn khi để nguyên dòng)
"""Dựng email (tiêu đề + text + HTML) cho cảnh báo, bản tin AI, báo cáo tuần, email thử (hàm thuần).

Chữ cố định theo ngôn ngữ báo cáo của tenant (`tenants.insight_language`, catalog `email.*`).
HTML dùng style nội tuyến và bảng (trình đọc email không hỗ trợ CSS ngoài), cùng màu thương hiệu
với dashboard: đầu tím than, liên kết tím, chữ mực. Không đưa thông tin kỹ thuật (mã lượt quét,
token, mô hình AI) vào email; mọi chữ động đều được escape.
"""

from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any

from app.i18n import DEFAULT_LOCALE, normalize_locale, t
from app.notify.alert_rules import AlertItem
from app.notify.fmt import fmt_night
from app.notify.weekly import WeeklyReport

NIGHT = "#16123a"
BRAND = "#673de6"
INK = "#1d1e20"
BODY = "#36344d"
MUTED = "#5e6072"
LINE = "#e3e1f0"
CANVAS = "#f4f5ff"
FONT = "'Be Vietnam Pro', -apple-system, 'Segoe UI', Roboto, Arial, sans-serif"

MAX_ITEMS = 30  # quá nhiều thì phần còn lại xem trên dashboard


@dataclass(frozen=True)
class Email:
    subject: str
    text: str
    html: str


def _subject(text: str) -> str:
    """Tiêu đề một dòng: tên khách sạn (dữ liệu scrape, nhãn do tenant nhập) có thể chứa xuống
    dòng, làm thư viện email từ chối header; gộp khoảng trắng và cắt độ dài."""
    s = " ".join(text.split())
    return s if len(s) <= 200 else s[:199].rstrip() + "…"


def _url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + path


def _layout(
    *,
    preheader: str,
    title: str,
    body_html: str,
    cta: tuple[str, str] | None,
    footer: str,
    locale: str,
) -> str:
    button = (
        f'<tr><td style="padding:8px 28px 28px"><a href="{escape(cta[0])}" '
        f'style="display:inline-block;background:{BRAND};color:#ffffff;text-decoration:none;'
        f'font:600 14px/1 {FONT};padding:12px 18px;border-radius:8px">{escape(cta[1])}</a></td></tr>'
        if cta
        else ""
    )
    return (
        f'<!doctype html><html lang="{normalize_locale(locale)}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        f'<body style="margin:0;background:{CANVAS}">'
        f'<span style="display:none;max-height:0;overflow:hidden">{escape(preheader)}</span>'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CANVAS}">'
        '<tr><td align="center" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:600px;background:#ffffff;border:1px solid {LINE};border-radius:12px;overflow:hidden">'
        f'<tr><td style="background:{NIGHT};padding:16px 28px;font:800 13px/1 {FONT};'
        'letter-spacing:.08em;color:#ffffff">SCRAPEBOOKING</td></tr>'
        f'<tr><td style="padding:24px 28px 8px;font:700 20px/1.35 {FONT};color:{INK}">{escape(title)}</td></tr>'
        f"{body_html}{button}"
        f'<tr><td style="padding:16px 28px;border-top:1px solid {LINE};font:400 12px/1.6 {FONT};color:{MUTED}">'
        f"{escape(footer)}</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def _footer(tenant_name: str, locale: str) -> str:
    return t(locale, "email.footer", tenant=tenant_name)


def render_alerts(
    tenant_name: str, items: list[AlertItem], base_url: str, locale: str = DEFAULT_LOCALE
) -> Email:
    shown = items[:MAX_ITEMS]
    more = len(items) - len(shown)
    first = items[0].headline
    subject = (
        first
        if len(items) == 1
        else t(locale, "email.alerts.subject_more", first=first, count=len(items) - 1)
    )
    title = t(locale, "email.alerts.title", count=len(items))

    text_lines = [title, ""]
    rows = []
    for it in shown:
        link = _url(base_url, f"/hotels/{it.hotel_id}/dates/{it.stay_date.isoformat()}")
        text_lines += [f"• {it.headline}: {it.detail}", f"  {link}"]
        rows.append(
            f'<tr><td style="padding:12px 0;border-bottom:1px solid {LINE}">'
            f'<div style="font:700 15px/1.45 {FONT};color:{INK}">{escape(it.headline)}</div>'
            f'<div style="font:400 14px/1.55 {FONT};color:{BODY}">{escape(it.detail)}</div>'
            f'<a href="{escape(link)}" style="font:600 13px/1.8 {FONT};color:{BRAND};text-decoration:none">'
            f"{escape(t(locale, 'email.alerts.view_night', night=fmt_night(it.stay_date, locale)))}"
            "</a></td></tr>"
        )
    if more > 0:
        more_text = t(locale, "email.alerts.more", count=more)
        text_lines.append(more_text)
        rows.append(
            f'<tr><td style="padding:12px 0;font:400 13px/1.6 {FONT};color:{MUTED}">'
            f"{escape(more_text)}</td></tr>"
        )
    events_url = _url(base_url, "/events")
    text_lines += [
        "",
        t(locale, "email.alerts.all_events", url=events_url),
        "",
        _footer(tenant_name, locale),
    ]
    body = (
        '<tr><td style="padding:0 28px 8px"><table role="presentation" width="100%" '
        f'cellpadding="0" cellspacing="0">{"".join(rows)}</table></td></tr>'
    )
    html = _layout(
        preheader=f"{first}. {items[0].detail}",
        title=title,
        body_html=body,
        cta=(events_url, t(locale, "email.alerts.cta")),
        footer=_footer(tenant_name, locale),
        locale=locale,
    )
    return Email(_subject(subject), "\n".join(text_lines), html)


def _first_sentence(text: str, limit: int = 70) -> str:
    s = text.strip().split(". ")[0].rstrip(".")
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def render_insight(
    tenant_name: str,
    insight_id: int,
    period_start: date,
    output: dict[str, Any],
    base_url: str,
    locale: str = DEFAULT_LOCALE,
) -> Email:
    """Nội dung do AI viết theo ngôn ngữ báo cáo (cùng `insight_language`); chữ khung dịch ở đây."""
    summary = str(output.get("summary") or "").strip()
    highlights = [h for h in output.get("highlights") or [] if isinstance(h, dict)][:5]
    day = f"{period_start.day:02d}/{period_start.month:02d}"
    heading = t(locale, "email.insight.title", day=day)
    subject = (
        t(locale, "email.insight.subject", day=day, summary=_first_sentence(summary))
        if summary
        else heading
    )
    link = _url(base_url, f"/insights/{insight_id}")
    rec_label = t(locale, "email.insight.recommendation")

    text_lines = [heading, "", summary, ""]
    rows = []
    for h in highlights:
        title = str(h.get("title") or "")
        rec = str(h.get("recommendation") or "")
        text_lines += [f"• {title}", f"  {rec_label} {rec}" if rec else ""]
        rows.append(
            f'<tr><td style="padding:12px 0;border-bottom:1px solid {LINE}">'
            f'<div style="font:700 15px/1.45 {FONT};color:{INK}">{escape(title)}</div>'
            + (
                f'<div style="margin-top:6px;padding:8px 12px;background:#f4f0ff;border-radius:8px;'
                f'font:400 14px/1.55 {FONT};color:{BODY}"><b style="color:#5025d1">{escape(rec_label)}</b> '
                f"{escape(rec)}</div>"
                if rec
                else ""
            )
            + "</td></tr>"
        )
    text_lines += [
        "",
        t(locale, "email.insight.read_full", url=link),
        "",
        _footer(tenant_name, locale),
    ]
    body = (
        f'<tr><td style="padding:0 28px 8px;font:400 16px/1.7 {FONT};color:{INK}">{escape(summary)}</td></tr>'
        + (
            '<tr><td style="padding:8px 28px"><table role="presentation" width="100%" '
            f'cellpadding="0" cellspacing="0">{"".join(rows)}</table></td></tr>'
            if rows
            else ""
        )
    )
    html = _layout(
        preheader=_first_sentence(summary, 140),
        title=heading,
        body_html=body,
        cta=(link, t(locale, "email.insight.cta")),
        footer=_footer(tenant_name, locale),
        locale=locale,
    )
    return Email(
        _subject(subject), "\n".join(line for line in text_lines if line is not None), html
    )


def _dm(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def _signed(v: int) -> str:
    return f"+{v}%" if v > 0 else (f"−{-v}%" if v < 0 else "0%")


def weekly_sections(
    r: WeeklyReport, locale: str = DEFAULT_LOCALE
) -> tuple[str, list[tuple[str, list[str]]]]:
    """(tiêu điểm cho tiêu đề email, các phần: tiêu đề phần + các dòng). Tên ngày lễ trong `r` đã
    theo ngôn ngữ."""
    c = r.counts

    def night(d: date) -> str:
        return fmt_night(d, locale)

    past: list[str] = []
    parts = [
        t(locale, f"email.weekly.count.{kind}", count=c[kind])
        for kind in ("sold_out", "low_stock_enter", "price_down", "price_up")
        if c[kind]
    ]
    past.append(
        t(locale, "email.weekly.competitors", parts=", ".join(parts))
        if parts
        else t(locale, "email.weekly.no_changes")
    )
    if r.busiest and parts:
        past.append(t(locale, "email.weekly.busiest", hotel=r.busiest[0], count=r.busiest[1]))

    ahead: list[str] = []
    if r.tight_nights:
        nights = "; ".join(
            t(locale, "email.weekly.tight_night", night=night(d), sold=s, observed=n)
            for d, s, n in r.tight_nights
        )
        ahead.append(t(locale, "email.weekly.tight_nights", nights=nights))
    elif r.nights_with_data:
        ahead.append(t(locale, "email.weekly.no_tight_nights"))
    if r.vs_median_avg is not None and r.vs_median_low and r.vs_median_high:
        ahead.append(
            t(
                locale,
                "email.weekly.vs_median",
                avg=_signed(r.vs_median_avg),
                low=_signed(r.vs_median_low[1]),
                low_night=night(r.vs_median_low[0]),
                high=_signed(r.vs_median_high[1]),
                high_night=night(r.vs_median_high[0]),
            )
        )
    if r.holidays:
        names = "; ".join(
            t(locale, "email.weekly.holiday", name=name, night=night(d)) for d, name in r.holidays
        )
        ahead.append(t(locale, "email.weekly.holidays", holidays=names))
    if not ahead:
        ahead.append(t(locale, "email.weekly.no_data"))

    if r.tight_nights:
        focus = t(locale, "email.weekly.focus.tight", count=len(r.tight_nights))
    elif c["sold_out"]:
        focus = t(locale, "email.weekly.focus.sold_out", count=c["sold_out"])
    elif parts:
        focus = t(locale, "email.weekly.focus.part", part=parts[0])
    else:
        focus = t(locale, "email.weekly.focus.quiet")
    sections = [
        (
            t(locale, "email.weekly.past", start=_dm(r.past_start), end=_dm(r.past_end)),
            past,
        ),
        (
            t(locale, "email.weekly.ahead", start=_dm(r.outlook_start), end=_dm(r.outlook_end)),
            ahead,
        ),
    ]
    return focus, sections


def render_weekly(
    tenant_name: str, report: WeeklyReport, base_url: str, locale: str = DEFAULT_LOCALE
) -> Email:
    focus, sections = weekly_sections(report, locale)
    heading = t(locale, "email.weekly.title", day=_dm(report.outlook_start))
    subject = t(locale, "email.weekly.subject", day=_dm(report.outlook_start), focus=focus)
    link = _url(base_url, "/overview?days=14")
    text_lines = [heading, ""]
    rows = []
    for heading, lines in sections:
        text_lines += [heading, *[f"• {line}" for line in lines], ""]
        rows.append(
            f'<tr><td style="padding:8px 28px 4px;font:700 15px/1.45 {FONT};color:{INK}">{escape(heading)}</td></tr>'
            + "".join(
                f'<tr><td style="padding:2px 28px 2px 40px;font:400 14px/1.6 {FONT};color:{BODY}">• {escape(line)}</td></tr>'
                for line in lines
            )
        )
    text_lines += [t(locale, "email.weekly.see_ahead", url=link), "", _footer(tenant_name, locale)]
    html = _layout(
        preheader=focus[:1].upper() + focus[1:],
        title=heading,
        body_html="".join(rows) + '<tr><td style="height:12px"></td></tr>',
        cta=(link, t(locale, "email.weekly.cta")),
        footer=_footer(tenant_name, locale),
        locale=locale,
    )
    return Email(_subject(subject), "\n".join(text_lines), html)


def render_test(tenant_name: str, base_url: str, locale: str = DEFAULT_LOCALE) -> Email:
    title = t(locale, "email.test.title")
    msg = t(locale, "email.test.body")
    link = _url(base_url, "/settings?tab=notifications")
    html = _layout(
        preheader=msg,
        title=title,
        body_html=f'<tr><td style="padding:0 28px 8px;font:400 15px/1.7 {FONT};color:{BODY}">{escape(msg)}</td></tr>',
        cta=(link, t(locale, "email.test.cta")),
        footer=_footer(tenant_name, locale),
        locale=locale,
    )
    footer = _footer(tenant_name, locale)
    return Email(_subject(title), f"{title}\n\n{msg}\n\n{link}\n\n{footer}", html)
