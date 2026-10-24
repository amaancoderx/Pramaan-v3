import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.config import settings
from app.schemas.rules import PassedCheck, ReasonDetail, RuleEvaluationResult
from app.schemas.verification import ExtractedData
from app.services.extractor import parse_clock, parse_datetime, words_to_number

KNOWN_DUMMY_UTRS = {"123456789012", "987654321098", "000000000000", "012345678901", "210987654321"}


@dataclass
class RuleContext:
    merchant_upi_id: str
    merchant_name: str
    allowed_window_minutes: int
    now: datetime                       # naive local time (settings.TIMEZONE)
    img_width: int = 0
    img_height: int = 0
    header_rgb: Optional[Tuple[int, int, int]] = None
    # "merchant": was this paid to me, recently? "authenticity": is the screenshot itself unedited?
    check_mode: str = "merchant"
    merchant_receiver_name: str = ""


# Checks about who was paid and when. They say nothing about editing, so in authenticity mode they are
# reported as information without risk points.
MERCHANT_ONLY_CODES = {"R_RECEIVER_MISMATCH", "R_RECEIVER_NAME_DIVERGENT", "R_RECEIVER_NOT_VISIBLE",
                       "R_TXN_EXPIRED", "R_DELAYED_SCREENSHOT"}
AUTHENTICITY_TITLES = {"R_RECEIVER_MISMATCH": "Paid to another UPI ID", "R_RECEIVER_NAME_DIVERGENT": "Paid to someone else",
                       "R_TXN_EXPIRED": "Older payment", "R_DELAYED_SCREENSHOT": "Screenshot taken later"}


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _receiver_name_matches(observed: str, expected_names: List[str]) -> bool:
    got = _norm_name(observed)
    if len(got) < 3:
        return False
    for expected in expected_names:
        want = _norm_name(expected)
        if len(want) >= 3 and (got == want or got in want or want in got):
            return True
        observed_tokens = set(re.findall(r"[a-z0-9]+", (observed or "").lower()))
        expected_tokens = set(re.findall(r"[a-z0-9]+", (expected or "").lower()))
        if len(observed_tokens) >= 2 and len(expected_tokens) >= 2:
            union = observed_tokens | expected_tokens
            if union and len(observed_tokens & expected_tokens) / len(union) >= 0.8:
                return True
    return False


def _status_class(text: str) -> str:
    """Return success/failure/unknown using whole words, avoiding substring mistakes."""
    s = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    negative = re.search(
        r"\b(?:failed|failure|pending|declined|processing|cancelled|canceled|reversed|unsuccessful|unpaid)\b"
        r"|\bnot\s+(?:successful|completed|paid|received)\b|\bcould\s+not\s+(?:complete|process)\b", s)
    if negative:
        return "failure"
    positive = re.search(r"\b(?:success|successful|successfully|paid|completed|complete|credited|received|sent)\b", s)
    return "success" if positive else "unknown"


def is_dummy_utr(utr: str) -> bool:
    if utr in KNOWN_DUMMY_UTRS or len(set(utr)) <= 2:
        return True
    # Long ascending / descending runs such as 345678901234
    best = run = 1
    prev_step = None
    for a, b in zip(utr, utr[1:]):
        step = (int(b) - int(a)) % 10
        if step in (1, 9) and step == prev_step:
            run += 1
        elif step in (1, 9):
            run = 2
        else:
            run = 1
        prev_step = step
        best = max(best, run)
    return best >= 8


class RulesEngine:
    def __init__(self, rules_file: Optional[str] = None):
        self.rules_file = rules_file or str(settings.RULES_PATH)
        with open(self.rules_file, "r", encoding="utf-8") as f:
            self.rules: Dict[str, Any] = yaml.safe_load(f)
        self.penalties: Dict[str, float] = self.rules["penalties"]
        self.defaults: Dict[str, Any] = self.rules["defaults"]

    def app_config(self, app: str) -> Dict[str, Any]:
        apps = self.rules["apps"]
        return apps.get(app, apps["generic"])

    def thresholds(self, strictness: str) -> Dict[str, float]:
        s = self.rules["strictness"]
        return s.get(strictness, s["standard"])

    def evaluate(self, ex: ExtractedData, ctx: RuleContext) -> RuleEvaluationResult:
        P = self.penalties
        app_cfg = self.app_config(ex.payment_app)
        reasons: List[ReasonDetail] = []
        passed: List[PassedCheck] = []
        validity: Dict[str, bool] = {}

        def fail(code, severity, title, message, penalty_key=None, field=None, evidence="field", value=None,
                 penalty=None):
            pen = penalty if penalty is not None else (P.get(penalty_key, 0) if penalty_key else 0)
            if ctx.check_mode == "authenticity" and code in MERCHANT_ONLY_CODES:
                severity, pen = "INFO", 0
                title = AUTHENTICITY_TITLES.get(code, title)
                message = (message.split(". ")[0].rstrip(".") + ". Shown for information: this check looks for "
                           "editing, not at who was paid or when.")
            box = getattr(ex, field).bbox if field and hasattr(ex, field) else None
            reasons.append(ReasonDetail(code=code, severity=severity, layer="rules", title=title, message=message,
                                        field=field, penalty=float(pen), evidence_type=evidence if field else None,
                                        evidence_value=value, region=box))
            if field and severity != "INFO":
                validity[field] = False

        def ok(code, title):
            passed.append(PassedCheck(code=code, layer="rules", title=title))

        if getattr(ex, "document_type", "unknown") == "history_list":
            fail("R_HISTORY_LIST_SCREEN", "MEDIUM" if ctx.check_mode == "merchant" else "INFO",
                 "Transaction history list detected",
                 "This image appears to show multiple payment-history rows rather than one transaction detail. "
                 "Pramaan does not combine fields from different rows, because that could create a false mismatch. "
                 "Open the specific transaction and verify its amount, receiver, UPI reference and status.",
                 field=None, penalty=20 if ctx.check_mode == "merchant" else 0)
            # A history list can contain many unrelated transactions. Do not compare a name from one row,
            # amount from another, and UTR from a third as if they belonged to one receipt.
            return RuleEvaluationResult(risk_score=20.0 if ctx.check_mode == "merchant" else 0.0,
                                        violations=reasons, passed=passed, extracted_fields_validity={})

        # 1. Amount
        amount_val: Optional[float] = None
        if not ex.amount.value:
            fail("R_AMT_MISSING", "HIGH", "Amount not found",
                 "No payment amount could be read on the screenshot.", "amount_missing", "amount")
        else:
            try:
                amount_val = float(str(ex.amount.value).replace(",", ""))
            except ValueError:
                amount_val = None
            if amount_val is None or amount_val <= 0:
                fail("R_AMT_INVALID", "CRITICAL", "Amount is not valid",
                     f"The amount '{ex.amount.value}' is not a valid payment amount.", "amount_invalid", "amount")
            else:
                validity["amount"] = True
                ok("R_AMT_PRESENT", "Amount is readable")

        # 2. Amount in digits vs words
        if amount_val and ex.amount_in_words.value:
            from_words = words_to_number(ex.amount_in_words.value)
            if from_words is not None and abs(from_words - amount_val) > 0.99:
                confident = ex.amount.confidence >= 0.85 and ex.amount_in_words.confidence >= 0.85
                fail("R_AMT_WORDS_MISMATCH", "CRITICAL" if confident else "HIGH",
                     "Amount in digits and words do not match",
                     f"Digits say ₹{amount_val:,.2f} but the words say ₹{from_words:,.2f}. "
                     + ("Both fields were read clearly, so one may have been edited."
                        if confident else "OCR confidence is low; check the amount manually before assuming editing."),
                     "amount_words_mismatch", "amount", value={"digits": amount_val, "words": from_words},
                     penalty=45 if confident else 25)
            elif from_words is not None:
                ok("R_AMT_WORDS_MATCH", "Amount in words matches the digits")

        # 3. UTR
        if not ex.utr.value:
            fail("R_UTR_MISSING", "HIGH", "UTR / reference number not found",
                 "A UPI payment always has a 12-digit reference number (UTR). None was found.", "utr_missing", "utr")
        else:
            utr = re.sub(r"\s", "", ex.utr.value)
            pattern = app_cfg.get("utr_pattern", r"^[0-9]{12}$")
            if not re.match(pattern, utr):
                fail("R_UTR_FORMAT_INVALID", "HIGH", "Reference format could not be verified",
                     f"'{utr}' does not match the usual reference format for {app_cfg.get('name', 'this app')}. "
                     "OCR or app-version differences can cause this; the format alone does not prove the screenshot "
                     "is fake. Verify the reference against the bank SMS or statement.",
                     "utr_invalid_format", "utr")
            elif utr.isdigit() and is_dummy_utr(utr):
                confident = ex.utr.confidence >= 0.85
                fail("R_UTR_DUMMY_SEQUENCE", "CRITICAL" if confident else "HIGH", "UTR looks made up",
                     f"'{utr}' resembles a repeating or counting sequence. "
                     + ("Fake-receipt generators commonly use numbers like this."
                        if confident else "OCR confidence is low; re-check the reference before treating it as fake."),
                     "utr_dummy_sequence", "utr", penalty=45 if confident else 25)
            else:
                validity["utr"] = True
                ok("R_UTR_FORMAT", "UTR has a valid UPI format")

        # 4. Receiver
        expected = (ctx.merchant_upi_id or "").lower().strip()
        if ex.receiver_upi_id.value:
            got = ex.receiver_upi_id.value.lower().strip()
            if expected and got != expected:
                fail("R_RECEIVER_MISMATCH", "CRITICAL", "Paid to a different UPI ID",
                     f"The screenshot shows payment to '{got}', but your UPI ID is '{expected}'. "
                     "This money did not come to you.", "receiver_mismatch", "receiver_upi_id",
                     value={"detected": got, "expected": expected})
            else:
                validity["receiver_upi_id"] = True
                ok("R_RECEIVER_MATCH", "Paid to your registered UPI ID")
        elif ex.receiver.value:
            allowed_names = [ctx.merchant_receiver_name, ctx.merchant_name]
            if _receiver_name_matches(ex.receiver.value, allowed_names):
                ok("R_RECEIVER_NAME_MATCH", "Receiver name matches your registered account or shop name")
                fail("R_RECEIVER_NOT_VISIBLE", "MEDIUM", "Receiver UPI ID not visible",
                     "The displayed receiver name matches your profile, but the UPI ID is not visible. A name can be copied; confirm the credit in your bank app.",
                     "receiver_not_visible", "receiver_upi_id")
            else:
                expected_name = ctx.merchant_receiver_name or ctx.merchant_name
                fail("R_RECEIVER_NAME_DIVERGENT", "HIGH", "Receiver name does not match your registered profile",
                     f"The screenshot shows '{ex.receiver.value}', which matches neither your registered account name nor shop name. Expected account name: '{expected_name}'.",
                     "receiver_name_divergent", "receiver", penalty=P["receiver_name_divergent"] + 15)
        else:
            fail("R_RECEIVER_NOT_VISIBLE", "MEDIUM", "Receiver not visible",
                 "Neither the receiver's UPI ID nor name could be read.", "receiver_not_visible", "receiver_upi_id")

        # 5. Transaction time vs now and the merchant's allowed window
        txn_dt = parse_datetime(ex.timestamp.value) if ex.timestamp.value else None
        if not ex.timestamp.value:
            fail("R_TIMESTAMP_MISSING", "MEDIUM", "Date and time not found",
                 "The payment date and time could not be read, so its age cannot be checked.",
                 "timestamp_missing", "timestamp")
        elif not txn_dt:
            fail("R_TIMESTAMP_MISSING", "MEDIUM", "Date and time unreadable",
                 f"'{ex.timestamp.value}' is not a recognisable date and time.", "timestamp_missing", "timestamp")
        else:
            delta_min = (ctx.now - txn_dt).total_seconds() / 60
            if delta_min < -self.defaults["future_tolerance_minutes"]:
                fail("R_TXN_FUTURE", "HIGH", "Payment time appears to be in the future",
                     f"The screenshot says {txn_dt:%d %b %Y, %I:%M %p}, which is later than the current time. "
                     "An OCR/date-format error is possible, so confirm the date and bank SMS before treating this "
                     "as evidence of editing.", "txn_future", "timestamp",
                     value={"transaction_time": txn_dt.isoformat(), "now": ctx.now.isoformat()})
            elif delta_min > ctx.allowed_window_minutes:
                age = _human_age(delta_min)
                fail("R_TXN_EXPIRED", "HIGH", "Payment is older than your allowed window",
                     f"This payment was made {age} ago. Your limit is {ctx.allowed_window_minutes} minutes. "
                     "Old screenshots are often reused.", "txn_expired", "timestamp",
                     value={"age_minutes": round(delta_min), "window": ctx.allowed_window_minutes})
            else:
                validity["timestamp"] = True
                ok("R_TXN_WINDOW", "Payment time is recent and within your window")

        # 5b. PhonePe transaction IDs start with the payment's own time: T + yyMMddHHmm. Editors change the date
        # line and leave the ID alone.
        tid = (ex.app_txn_id.value or "") if ex.app_txn_id else ""
        tid_dt = _txn_id_time(tid)
        if txn_dt and tid_dt:
            gap = abs((tid_dt - txn_dt).total_seconds()) / 60
            if gap <= self.defaults["clock_tolerance_minutes"]:
                ok("R_TXN_ID_TIME_MATCH", "Transaction ID matches the payment date and time")
            else:
                fail("R_TXN_ID_TIME_MISMATCH", "HIGH", "Date differs from the embedded transaction-ID time",
                     f"The transaction ID suggests {tid_dt:%d %b %Y, %I:%M %p}, while the screenshot shows "
                     f"{txn_dt:%d %b %Y, %I:%M %p}. App versions, OCR, or reference formats can differ; treat this "
                     "as a warning and confirm with the bank SMS rather than proof of editing.",
                     "txn_id_time_mismatch", "timestamp", value={"id_time": tid_dt.isoformat(), "shown": txn_dt.isoformat()},
                     penalty=25)

        # 6. Status-bar clock vs transaction time
        if txn_dt and ex.status_bar_time.value:
            clock = parse_clock(ex.status_bar_time.value)
            if clock:
                sb_min = clock[0] * 60 + clock[1]
                tx_min = txn_dt.hour * 60 + txn_dt.minute
                # Minutes from payment to screenshot (mod 24h). A 12-hour clock without AM/PM
                # ("2:36") is ambiguous, so both readings are considered.
                raw = ex.status_bar_time.value.strip().lower()
                ambiguous = clock[0] < 12 and not raw.startswith("0") and "m" not in raw
                cands = [(sb_min - tx_min) % 1440]
                if ambiguous:
                    cands.append((sb_min + 720 - tx_min) % 1440)
                tol = self.defaults["clock_tolerance_minutes"]
                delayed_limit = self.defaults["delayed_screenshot_hours"] * 60
                normal = [c for c in cands if c <= delayed_limit or 1440 - c <= tol]
                before = [1440 - c for c in cands if c > 720]
                if normal:
                    ok("R_CLOCK_CONSISTENT", "Phone clock is consistent with payment time")
                elif before:
                    fail("R_CLOCK_INCONSISTENCY", "HIGH", "Screenshot taken before the payment",
                         f"The phone clock shows {ex.status_bar_time.value}, but the payment time is "
                         f"{txn_dt:%I:%M %p}, {min(before)} minutes later. A screenshot cannot be taken "
                         "before the payment happens.", "clock_inconsistent", "status_bar_time")
                else:
                    fail("R_DELAYED_SCREENSHOT", "LOW", "Screenshot taken hours after payment",
                         f"The phone clock is about {min(cands) // 60} hours after the payment time.",
                         "delayed_screenshot", "status_bar_time")

        # 7. Status
        if ex.status.value:
            status_kind = _status_class(ex.status.value)
            if status_kind != "success":
                confident = ex.status.confidence >= 0.85
                fail("R_STATUS_NOT_SUCCESS", "HIGH" if confident else "MEDIUM",
                     "Payment is not marked successful",
                     f"The readable status is '{ex.status.value}', which does not clearly confirm success. A genuine screenshot can show a failed or pending payment; verify the bank credit before accepting it.",
                     "status_not_success", "status", penalty=50 if confident else 25)
            else:
                validity["status"] = True
                ok("R_STATUS_SUCCESS", "Status says the payment succeeded")
        else:
            fail("R_STATUS_MISSING", "LOW", "Success status not found",
                 "No 'payment successful' style status was found.", "status_missing", "status")

        # 8. OCR confidence on the fields that matter
        min_conf = self.defaults["min_field_confidence"]
        for name in ("amount", "utr"):
            f = getattr(ex, name)
            if f.value and not f.corrected and f.confidence < min_conf:
                fail("R_LOW_CONFIDENCE", "MEDIUM", f"{name.upper() if name == 'utr' else 'Amount'} hard to read",
                     f"'{f.value}' was read with {f.confidence * 100:.0f}% confidence. Check it against the "
                     "customer's phone.", "low_confidence", name)

        # 9. Layout template. Only for an identified app: an unknown app has no template to compare against,
        # and real apps differ by version (Paytm left-aligns the amount, for example).
        # Only enforce a visual template when this app has an explicitly configured layout.
        # New/recognised UPI apps otherwise fall back to generic field-format checks, not a fake layout mismatch.
        layout = app_cfg.get("layout", {}) if ex.payment_app in self.rules["apps"] and ex.payment_app != "generic" else {}
        deviations = self._layout_deviations(ex, layout, ctx) if layout else []
        if deviations:
            fail("R_LAYOUT_MISMATCH", "LOW", "Layout differs from the usual receipt",
                 "Compared with the expected layout for " + app_cfg.get("name", "this app") + ": "
                 + "; ".join(deviations) + ".", "layout_mismatch")
        elif ctx.img_height:
            ok("R_LAYOUT_MATCH", "Layout matches the expected receipt template")

        score = min(100.0, sum(r.penalty for r in reasons))
        return RuleEvaluationResult(risk_score=round(score, 1), violations=reasons, passed=passed,
                                    extracted_fields_validity=validity)

    @staticmethod
    def _layout_deviations(ex: ExtractedData, layout: Dict[str, Any], ctx: RuleContext) -> List[str]:
        out: List[str] = []
        if not ctx.img_height or not ex.amount.bbox:
            return out
        # Positions are fractions of a full phone screen; a cropped screenshot has no fixed frame.
        if ctx.img_width and max(ctx.img_width, ctx.img_height) / min(ctx.img_width, ctx.img_height) < 1.55:
            return out
        b = ex.amount.bbox
        cy = (b.y + b.height / 2) / ctx.img_height
        lo, hi = layout.get("amount_y_range", [0.0, 1.0])
        if not lo <= cy <= hi:
            out.append(f"the amount sits at {cy * 100:.0f}% of the screen height")
        if layout.get("amount_centered") and ctx.img_width:
            cx = (b.x + b.width / 2) / ctx.img_width
            if abs(cx - 0.5) > 0.15:
                out.append("the amount is not centred")
        if layout.get("status_above_amount") and ex.status.bbox and ex.status.bbox.y > b.y:
            out.append("the status line is below the amount")
        expected_rgb = layout.get("header_rgb")
        # A near-black header is the app's dark mode, not a different theme.
        if expected_rgb and ctx.header_rgb and max(ctx.header_rgb) > 45:
            dist = sum((a - c) ** 2 for a, c in zip(ctx.header_rgb, expected_rgb)) ** 0.5
            if dist > 120:
                out.append("header colours differ from this app's theme")
        return out


def _txn_id_time(tid: str) -> Optional[datetime]:
    m = re.fullmatch(r"T(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\d{10,13}", tid or "")
    if not m:
        return None
    try:
        yy, mo, dd, hh, mi = (int(g) for g in m.groups())
        return datetime(2000 + yy, mo, dd, hh, mi)
    except ValueError:
        return None


def _human_age(minutes: float) -> str:
    if minutes < 120:
        return f"{minutes:.0f} minutes"
    if minutes < 48 * 60:
        return f"{minutes / 60:.0f} hours"
    return f"{minutes / 1440:.0f} days"


rules_engine = RulesEngine()
