"""Parse Indian bank credit SMS / UPI notifications and match them against a checked screenshot."""
import re
from typing import Any, Dict, Optional

from app.services.extractor import parse_datetime

BANKS = ["HDFC", "SBI", "ICICI", "AXIS", "KOTAK", "PNB", "BOB", "BANK OF BARODA", "CANARA", "UNION", "IDFC",
         "YES BANK", "INDUSIND", "FEDERAL", "IDBI", "PAYTM", "AIRTEL", "INDIAN BANK", "CENTRAL BANK", "UCO"]

CREDIT_WORDS = re.compile(r"\b(credited|credit(?:ed)?\s+to|received|deposited|added\s+to)\b", re.I)
DEBIT_WORDS = re.compile(r"\b(debited|debit(?:ed)?\s+from|withdrawn|sent|paid\s+to|spent|deducted)\b", re.I)

_AMT = r"(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
AMOUNT_PATTERNS = [
    re.compile(r"(?:rs\.?|inr|₹)\s*" + _AMT, re.I),
    re.compile(_AMT + r"\s*(?:rs\.?|inr|/-)", re.I),
    re.compile(r"(?:credited|received|deposited)\s+(?:with|by|for|of)?\s*" + _AMT, re.I),
]
UTR_PATTERNS = [
    re.compile(r"(?:utr|rrn|upi\s*ref(?:erence)?(?:\s*no\.?)?|ref(?:erence)?\s*(?:no|id)?\.?|txn\s*(?:id|no)?|"
               r"transaction\s*id|upi)[\s:/#.\-]*(?:cr/|dr/)?(\d{12})(?!\d)", re.I),
    re.compile(r"upi/(?:cr|p2a|p2m)?/?(\d{12})(?!\d)", re.I),
    re.compile(r"(?<!\d)(\d{12})(?!\d)"),
]
ACCOUNT_RE = re.compile(r"(?:a/?c|acct|account)(?:\s*no\.?)?\s*(?:ending\s*(?:with)?\s*)?[:\s]*([x*]*\d{3,18})", re.I)


def mask_sensitive(text: str) -> str:
    """Mask account and phone numbers before anything is stored. 12-digit UTRs are kept (needed for matching)."""
    if not text:
        return text

    def _acct(m: re.Match) -> str:
        return m.group(0).replace(m.group(1), "XX" + m.group(1)[-4:]) if len(m.group(1)) > 4 else m.group(0)

    text = ACCOUNT_RE.sub(_acct, text)

    def _long(m: re.Match) -> str:
        d = m.group(0)
        if len(d) == 12:
            return d
        return "X" * (len(d) - 4) + d[-4:]

    return re.sub(r"(?<!\d)\d{9,18}(?!\d)", _long, text)


def parse_sms(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"parsed": False, "direction": None, "amount": None, "utr": None,
                              "account_masked": None, "bank": None, "time": None}
    if not text or not text.strip():
        return result
    t = " ".join(text.split())

    credit, debit = CREDIT_WORDS.search(t), DEBIT_WORDS.search(t)
    if credit and debit:
        # "debited from A ... credited to B": whichever comes first describes the account holder.
        result["direction"] = "credit" if credit.start() < debit.start() else "debit"
    elif credit:
        result["direction"] = "credit"
    elif debit:
        result["direction"] = "debit"

    for pat in AMOUNT_PATTERNS:
        m = pat.search(t)
        if m:
            try:
                result["amount"] = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                continue
    for pat in UTR_PATTERNS:
        m = pat.search(t)
        if m:
            result["utr"] = m.group(1)
            break
    acc = ACCOUNT_RE.search(t)
    if acc:
        result["account_masked"] = "XX" + acc.group(1)[-4:]
    up = t.upper()
    result["bank"] = next((b for b in BANKS if re.search(r"\b" + re.escape(b) + r"\b", up)), None)
    dt = parse_datetime(t)
    result["time"] = dt.isoformat() if dt else None
    result["parsed"] = result["amount"] is not None or result["utr"] is not None
    return result


def match(sms: Dict[str, Any], amount: Optional[float], utr: Optional[str]) -> Dict[str, Any]:
    """Returns {status, code, severity, title, message, penalty, amount_matched, utr_matched}."""
    sms_amt, sms_utr = sms.get("amount"), sms.get("utr")
    amt_ok = amount is not None and sms_amt is not None and abs(amount - sms_amt) < 0.01
    utr_ok = bool(utr and sms_utr and utr.strip() == sms_utr.strip())
    base = {"amount_matched": amt_ok if sms_amt is not None else None,
            "utr_matched": utr_ok if sms_utr is not None else None}

    if sms.get("direction") == "debit":
        return {**base, "status": "SMS_MISMATCH", "code": "GT_SMS_MISMATCH", "severity": "HIGH", "penalty": 30.0,
                "title": "This SMS is a debit, not a credit",
                "message": "The message says money was debited or sent, so it does not prove you received this "
                           "payment. Paste the credit SMS from your bank."}
    if utr_ok and amt_ok:
        return {**base, "status": "SMS_MATCHED", "code": "GT_SMS_MATCHED", "severity": "INFO", "penalty": 0.0,
                "title": "Bank SMS confirms this payment",
                "message": f"Your bank SMS shows ₹{sms_amt:,.2f} credited with UTR {sms_utr}, the same as the "
                           "screenshot."}
    if utr_ok and sms_amt is not None and not amt_ok:
        return {**base, "status": "SMS_MISMATCH", "code": "GT_SMS_AMOUNT_MISMATCH", "severity": "CRITICAL",
                "penalty": 50.0, "title": "Bank received a different amount",
                "message": f"Same UTR, but your bank received ₹{sms_amt:,.2f} while the screenshot shows "
                           f"₹{amount:,.2f}" if amount is not None else "Same UTR, but the amount differs."}
    if sms_utr and utr and not utr_ok:
        return {**base, "status": "SMS_MISMATCH", "code": "GT_SMS_MISMATCH", "severity": "HIGH", "penalty": 30.0,
                "title": "SMS is for a different payment",
                "message": f"The SMS has UTR {sms_utr} but the screenshot shows {utr}. They are not the same "
                           "transaction."}
    if not sms_utr:
        return {**base, "status": "SMS_MISMATCH", "code": "GT_SMS_MISMATCH", "severity": "MEDIUM", "penalty": 15.0,
                "title": "SMS has no UTR to match",
                "message": "The SMS does not include a 12-digit UPI reference, so it cannot confirm this exact "
                           "payment." + (" The amount does match." if amt_ok else "")}
    return {**base, "status": "SMS_MISMATCH", "code": "GT_SMS_MISMATCH", "severity": "HIGH", "penalty": 30.0,
            "title": "SMS could not be matched",
            "message": "The screenshot has no readable UTR, so the SMS cannot be tied to it. Correct the UTR "
                       "field and try again."}
