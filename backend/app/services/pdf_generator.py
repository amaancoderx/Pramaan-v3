import io
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import settings
from app.services.mock_receipts import FONT_BOLD, FONT_REGULAR

pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_REGULAR)))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_BOLD)))

INK = colors.HexColor("#0E1A2B")
MUTED = colors.HexColor("#5B6575")
LINE = colors.HexColor("#E4E0D6")
PAPER = colors.HexColor("#F6F4EF")
VERDICT_COLORS = {"CONFIRMED": "#0F7B4F", "LIKELY GENUINE": "#2563A8", "SUSPICIOUS": "#B26B00", "LIKELY FAKE": "#C2302B"}
SEVERITY_COLORS = {"CRITICAL": "#C2302B", "HIGH": "#B26B00", "MEDIUM": "#8A6D1F", "LOW": "#2563A8", "INFO": "#5B6575"}
INSTRUCTIONS = {
    "CONFIRMED": "Bank SMS matches this payment. You can hand over goods.",
    "LIKELY GENUINE": "Looks clean but is not confirmed. Check your bank SMS or soundbox before handing over goods.",
    "SUSPICIOUS": "Do not hand over goods yet. Confirm in your bank app.",
    "LIKELY FAKE": "Do not hand over goods. Confirm in your bank app.",
}
LAYER_NAMES = {"forensics": "Image forensics", "rules": "Payment rules", "ground_truth": "Bank SMS",
               "duplicate": "Reuse check"}


def _s(name: str, **kw) -> ParagraphStyle:
    base = dict(fontName="DejaVu", fontSize=9, leading=12.5, textColor=INK)
    base.update(kw)
    return ParagraphStyle(name, **base)


H1 = _s("h1", fontName="DejaVu-Bold", fontSize=15, leading=19)
SMALL = _s("small", fontSize=7.5, leading=10, textColor=MUTED)
BODY = _s("body")
BOLD = _s("bold", fontName="DejaVu-Bold")
SECTION = _s("section", fontName="DejaVu-Bold", fontSize=10, leading=14, spaceBefore=8, spaceAfter=4)


def _p(text: Any, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text)) if text is not None else "-", style)


def _qr(data: str, size: float) -> RLImage:
    q = qrcode.QRCode(box_size=4, border=1)
    q.add_data(data)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    buf.seek(0)
    return RLImage(buf, width=size, height=size)


def _thumb(path: Optional[str], max_h: float) -> Optional[RLImage]:
    if not path or not os.path.exists(path):
        return None
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    height = max_h
    return RLImage(path, width=height * w / h, height=height)


def generate_report(v: Dict[str, Any], merchant_name: str, image_path: Optional[str],
                    heatmap_path: Optional[str]) -> bytes:
    """`v` is a VerificationResponse dict."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f"Pramaan report {v['id']}", author="Pramaan")
    width = A4[0] - 32 * mm
    tz = ZoneInfo(settings.TIMEZONE)
    created = datetime.fromisoformat(str(v["created_at"]).replace("Z", "")).replace(tzinfo=ZoneInfo("UTC"))
    verdict = v["verdict"]
    vcol = colors.HexColor(VERDICT_COLORS.get(verdict, "#5B6575"))
    el: List[Any] = []

    head = Table([[
        [_p("Pramaan", H1), _p("Payment screenshot verification report", SMALL)],
        [_p(f"Report ID  {v['id']}", BOLD),
         _p(f"Checked {created.astimezone(tz):%d %b %Y, %I:%M %p} IST · for {merchant_name}", SMALL)],
    ]], colWidths=[width * 0.45, width * 0.55])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    el += [head, Spacer(1, 8)]

    band = Table([[
        _p(verdict, _s("v", fontName="DejaVu-Bold", fontSize=18, leading=22, textColor=colors.white)),
        _p(f"Risk {v['risk_score']:.0f}/100", _s("r", fontName="DejaVu-Bold", fontSize=11, textColor=colors.white,
                                                 alignment=2)),
    ], [_p(INSTRUCTIONS.get(verdict, ""), _s("i", textColor=colors.white, fontSize=10)), ""]],
        colWidths=[width * 0.7, width * 0.3])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), vcol), ("SPAN", (0, 1), (1, 1)),
                              ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                              ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                              ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el += [band, Spacer(1, 4), _p(v.get("final_verdict_reason"), SMALL)]

    ex = v["extracted_data"]
    rows = [[_p("Field", BOLD), _p("Value", BOLD), _p("OCR confidence", BOLD), _p("Check", BOLD)]]
    for key, label in [("amount", "Amount"), ("utr", "UTR / reference"), ("timestamp", "Date and time"),
                       ("receiver", "Paid to"), ("receiver_upi_id", "Receiver UPI ID"), ("sender", "From"),
                       ("status", "Status"), ("amount_in_words", "Amount in words")]:
        f = ex.get(key) or {}
        val = f.get("value")
        if key == "amount" and val:
            val = f"Rs. {float(val):,.2f}"
        check = "corrected by merchant" if f.get("corrected") else ("ok" if f.get("is_valid") else "flagged")
        rows.append([_p(label), _p(val), _p(f"{(f.get('confidence') or 0) * 100:.0f}%" if val else "-"),
                     _p(check if val else "not found", SMALL)])
    t = Table(rows, colWidths=[width * 0.22, width * 0.45, width * 0.15, width * 0.18])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), PAPER),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el += [_p("Extracted details", SECTION), t]

    el.append(_p("Findings (most serious first)", SECTION))
    reasons = v.get("reasons") or []
    if reasons:
        rrows = []
        for r in reasons:
            sev = r["severity"]
            rrows.append([
                Paragraph(f"<font color='{SEVERITY_COLORS.get(sev, '#5B6575')}'><b>{sev}</b></font>",
                          _s("sev", fontName="DejaVu-Bold", fontSize=7.5)),
                [_p(r["title"], BOLD), _p(r["message"], SMALL)],
                _p(LAYER_NAMES.get(r.get("layer"), r.get("layer")), SMALL),
                _p(f"+{r['penalty']:.0f}" if r.get("penalty") else "", SMALL),
            ])
        rt = Table(rrows, colWidths=[width * 0.12, width * 0.6, width * 0.18, width * 0.1])
        rt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        el.append(rt)
    else:
        el.append(_p("No problems were found by the image, rules or reuse checks.", BODY))
    passed = v.get("passed_checks") or []
    if passed:
        el.append(Spacer(1, 4))
        el.append(_p("Passed: " + "; ".join(p["title"] for p in passed) + ".", SMALL))

    gt = v.get("ground_truth") or {}
    el.append(_p("Bank confirmation", SECTION))
    el.append(_p(gt.get("message") or "No bank SMS was matched for this check. A screenshot alone does not prove "
                 "that money reached your account.", BODY))

    verify_url = f"{settings.PUBLIC_APP_URL.rstrip('/')}/verify/{v['id']}"
    shot, heat = _thumb(image_path, 62 * mm), _thumb(heatmap_path, 62 * mm)
    cells = []
    if shot:
        cells.append([shot, _p("Screenshot", SMALL)])
    if heat:
        cells.append([heat, _p("Error-level heatmap (bright = edited or re-compressed)", SMALL)])
    cells.append([_qr(verify_url, 30 * mm), _p("Scan to open the public record of this check", SMALL),
                  _p(verify_url, _s("u", fontSize=6.5, leading=8, textColor=MUTED))])
    ev = Table([cells], colWidths=[width / len(cells)] * len(cells))
    ev.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    el += [_p("Evidence", SECTION), ev, Spacer(1, 10)]

    el.append(_p("A screenshot alone cannot prove a payment. Only a matching bank SMS or your bank app confirms "
                 "that money was received. Screenshots are deleted from Pramaan after "
                 f"{settings.RETENTION_HOURS} hours; account numbers are masked in stored text.", SMALL))
    doc.build(el)
    return buf.getvalue()
