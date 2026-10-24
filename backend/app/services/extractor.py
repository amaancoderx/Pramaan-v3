import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.rules import BoundingBox
from app.schemas.verification import ExtractedData, ExtractedField

Item = Dict[str, Any]

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
SCALES = {"hundred": 100, "thousand": 1000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000,
          "crore": 10_000_000, "crores": 10_000_000}


def _words_value(tokens: List[str]) -> Tuple[int, bool]:
    total, current, found = 0, 0, False
    for tok in tokens:
        if tok in NUMBER_WORDS:
            current += NUMBER_WORDS[tok]
            found = True
        elif tok == "hundred":
            current = max(1, current) * 100
            found = True
        elif tok in SCALES:
            total += max(1, current) * SCALES[tok]
            current = 0
            found = True
    return total + current, found


_VOCAB = sorted(set(NUMBER_WORDS) | set(SCALES) | {"hundred", "rupees", "rupee", "only", "and", "paise"},
                key=len, reverse=True)


def _split_merged(token: str) -> List[str]:
    """OCR often drops spaces: 'rupeesfourhundredfifty' -> ['rupees', 'four', 'hundred', 'fifty']."""
    out, i = [], 0
    while i < len(token):
        word = next((w for w in _VOCAB if token.startswith(w, i)), None)
        if not word:
            return [token]  # not made of number words; leave untouched
        out.append(word)
        i += len(word)
    return out


def words_to_number(text: str) -> Optional[float]:
    """'Rupees One Thousand Two Hundred Fifty and Fifty Paise Only' -> 1250.5 (Indian numbering)."""
    cleaned = re.sub(r"[^a-z\s]", " ", text.lower())
    tokens = [w for t in cleaned.split() for w in _split_merged(t)]
    tokens = [t for t in tokens if t not in ("rupees", "rupee", "rs", "inr", "only")]
    paise = 0
    if "paise" in tokens:
        idx = tokens.index("paise")
        head = tokens[:idx]
        if "and" in head:
            cut = len(head) - 1 - head[::-1].index("and")
            paise, _ = _words_value(head[cut + 1:])
            tokens = head[:cut]
        else:
            tokens = head
    tokens = [t for t in tokens if t != "and"]
    rupees, found = _words_value(tokens)
    if not found or rupees + paise == 0:
        return None
    return float(rupees) + paise / 100.0


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _fix_month(tok: str) -> str:
    # OCR commonly confuses O/0, S/5 and I/1 in month abbreviations.
    return tok.lower().replace("0", "o").replace("5", "s").replace("1", "l")[:3]


_TIME = r"(?P<hh>[0-2]?\d)[:.](?P<mm>[0-5]\d)(?::[0-5]\d)?\s*(?P<ampm>[ap]\.?m\.?)?"
_YEAR = r"(?P<y>(?:20)?\d{2})"
_MONTH = r"(?P<mon>[A-Za-z015]{3})[A-Za-z]*"
_DT_PATTERNS = [
    # 23 Oct 2026, 02:32 PM; 23rd Oct 26, 03:08 pm; compact OCR such as 230ct2026,02:32AM.
    re.compile(r"(?P<d>[0-3]?\d)\s*" + _MONTH + r"\.?\s*,?\s*['’]?" + _YEAR + r"\s*[,|\s-]*\s*(?:at\s*)?" + _TIME, re.I),
    # Oct 23, 2026 2:32 PM / Oct 23rd '26, 2:32 PM
    re.compile(_MONTH + r"\.?\s*(?P<d>[0-3]?\d)\s*,?\s*['’]?" + _YEAR + r"\s*[,|\s-]*\s*(?:at\s*)?" + _TIME, re.I),
    # 2:32 PM on 23 Oct 2026
    re.compile(_TIME + r"\s*(?:on|,)?\s*(?P<d>[0-3]?\d)\s*" + _MONTH + r"\.?\s*,?\s*['’]?" + _YEAR, re.I),
    # 23/10/2026 14:32 | 23-10-26 2:32 pm
    re.compile(r"(?P<d>[0-3]?\d)[/\-.](?P<mo>[01]?\d)[/\-.](?P<y>(?:20)?\d{2})\s*[,|\s]*\s*" + _TIME, re.I),
]


def parse_datetime(text: str) -> Optional[datetime]:
    """Parse common Indian UPI timestamp formats, including ordinal days and two-digit years."""
    if not text:
        return None
    normalized = str(text).replace("’", "'").replace("‘", "'")
    normalized = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", normalized, flags=re.I)
    normalized = re.sub(r"(?<=\d)\s*[,']\s*(?=(?:20)?\d{2}\b)", " ", normalized)
    for pat in _DT_PATTERNS:
        m = pat.search(normalized)
        if not m:
            continue
        g = m.groupdict()
        try:
            month = int(g["mo"]) if g.get("mo") else MONTHS.get(_fix_month(g["mon"]))
            if not month:
                continue
            year = int(g["y"])
            year = year + 2000 if year < 100 else year
            hh, mm = int(g["hh"]), int(g["mm"])
            ampm = (g.get("ampm") or "").lower().replace(".", "")
            if ampm == "pm" and hh < 12:
                hh += 12
            elif ampm == "am" and hh == 12:
                hh = 0
            return datetime(year, month, int(g["d"]), hh, mm)
        except (ValueError, TypeError):
            continue
    return None


def parse_clock(text: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"\b([0-2]?\d)[:.]([0-5]\d)\s*([ap]m)?\b", text or "", re.I)
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hh < 12:
        hh += 12
    elif ampm == "am" and hh == 12:
        hh = 0
    return (hh, mm) if hh < 24 else None


VPA_RE = re.compile(r"([a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9]{1,63})")
TRAILING_AMOUNT_RE = re.compile(r"[A-Za-z)]\s*(?:₹|rs\.?|\?)\s*(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?)$", re.I)
APP_TXN_RE = re.compile(r"(?<![0-9A-Za-z])(T\d{20,23})(?!\d)")
AMOUNT_RE = re.compile(r"^(?P<cur>₹|rs\.?|inr|[^\w\s,.]{1,2}|[A-Za-z一-鿿]{1})?\s*"
                       r"(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d{1,6}(?:\.\d{1,2})?)\s*(?:/-)?$", re.I)
UTR_LABELS = ("utr", "upi ref", "ref no", "ref. no", "reference", "transaction id", "txn id", "rrn",
              "upi transaction id", "transactionid", "refno", "upi ref id", "bank reference")
TO_LABELS = ("paid to", "sent to", "paying", "transfer to", "to:", "payee", "received by",
             "banking name", "bank name", "account name", "account holder", "beneficiary name", "beneficiary",
             "receiver name", "payee name", "credited to")
FROM_LABELS = ("from", "debited from", "paid by", "sender")
NOTE_LABELS = ("note", "message", "remarks", "description")
SUCCESS_WORDS = ("successful", "success", "completed", "complete", "paid", "credited", "received", "sent")
FAIL_WORDS = ("failed", "failure", "pending", "declined", "processing", "cancelled", "reversed", "unsuccessful")
HISTORY_MARKERS = (
    "balance & history", "balance and history", "payment history", "transaction history",
    "see transaction history", "all transactions", "recent transactions", "payment activity", "passbook",
)


def looks_like_history_list(items: List[Item]) -> bool:
    """Recognise a list of transactions so one row is not falsely treated as a full receipt."""
    texts = [str(i.get("text", "")) for i in items]
    joined = " ".join(texts).lower()
    compact = re.sub(r"[^a-z0-9]+", " ", joined)
    has_history_marker = any(re.sub(r"[^a-z0-9]+", " ", marker.lower()).strip() in compact
                             for marker in HISTORY_MARKERS)
    # Some versions only say "Transactions" or "Activity" at the top of a history list.
    if not has_history_marker:
        has_history_marker = bool(re.search(r"\b(?:transactions|activity)\b", compact))
    if not has_history_marker:
        return False

    amount_rows = 0
    status_rows = 0
    date_rows = 0
    for text in texts:
        squashed = text.strip().replace(" ", "")
        if re.search(r"(?:₹|rs\.?|inr|[-+]₹)\s*[-+]?\s*\d[\d,]*(?:\.\d{1,2})?", text, re.I):
            amount_rows += 1
        elif AMOUNT_RE.match(squashed) and re.search(r"\d", squashed):
            amount_rows += 1
        if _status_kind(text) != "unknown":
            status_rows += 1
        if parse_datetime(text) or re.search(
            r"\b(?:today|yesterday|mon|tue|wed|thu|fri|sat|sun)\b", text, re.I
        ) or re.search(r"\b\d{1,2}\s+[A-Za-z]{3,9}\b", text):
            date_rows += 1
    return amount_rows >= 2 and (status_rows >= 2 or date_rows >= 2 or amount_rows >= 4)

APP_KEYWORDS = [
    ("phonepe", ("phonepe", "phone pe")),
    ("gpay", ("google pay", "googlepay", "gpay", "g pay")),
    ("paytm", ("paytm",)),
    ("bhim", ("bhim", "bharat's own payments app")),
    ("fampay", ("fampay", "fam pay", "famapp", "fam app", "famcoins", "fam coin")),
    ("amazonpay", ("amazon pay", "amazonpay")),
    ("whatsapppay", ("whatsapp pay", "whats app pay", "whatsapppay")),
    ("mobikwik", ("mobikwik", "mobi kwik")),
    ("cred", ("cred pay", "cred")),
    ("navi", ("navi upi", "navi")),
    ("payzapp", ("payzapp", "pay zapp")),
    ("freecharge", ("freecharge", "free charge")),
    ("supermoney", ("super.money", "supermoney", "super money")),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def _has_label(text: str, labels) -> bool:
    t = _norm(text)
    return any(_norm(lbl) in t for lbl in labels)


def _status_kind(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    if re.search(r"\b(?:failed|failure|pending|declined|processing|cancelled|canceled|reversed|unsuccessful|unpaid)\b"
                 r"|\bnot\s+(?:successful|completed|paid|received)\b", s):
        return "failure"
    if re.search(r"\b(?:success|successful|successfully|paid|completed|complete|credited|received)\b", s):
        return "success"
    return "unknown"


class UPIExtractor:
    @staticmethod
    def identify_payment_app(items: List[Item]) -> str:
        # UPI handles such as name@paytm or name@ybl say nothing about which app produced the screenshot.
        full = " ".join(VPA_RE.sub(" ", i["text"]).lower() for i in items)
        words = set(re.findall(r"[a-z0-9]+", full))
        normalized_phrase = re.sub(r"[^a-z0-9]+", " ", full)
        for app, keys in APP_KEYWORDS:
            for key in keys:
                key_words = re.findall(r"[a-z0-9]+", key.lower())
                compact_key = "".join(key_words)
                # Single short brands such as "cred" and "navi" must match as whole OCR tokens,
                # not inside unrelated words like "credited" or a receiver's name.
                if len(key_words) == 1 and key_words[0] in words:
                    return app
                if len(key_words) > 1 and " ".join(key_words) in normalized_phrase:
                    return app
                if len(key_words) > 1 and compact_key in "".join(re.findall(r"[a-z0-9]+", full)):
                    return app
        # PhonePe's receipt may show its logo as an image, so OCR cannot always read the brand.
        # Its T-prefixed transaction reference is a fallback, though it does not prove the source app.
        if any(APP_TXN_RE.search(re.sub(r"\s+", "", i["text"])) for i in items):
            return "phonepe"
        return "generic"

    @staticmethod
    def _field(item: Optional[Item], value: Optional[str] = None, conf: Optional[float] = None) -> ExtractedField:
        if not item:
            return ExtractedField(value=None, confidence=0.0, bbox=None, is_valid=False)
        return ExtractedField(value=value if value is not None else item["text"],
                              confidence=round(conf if conf is not None else item["confidence"], 4),
                              bbox=BoundingBox(**item["bbox"]), is_valid=True)

    @staticmethod
    def _after_label(items: List[Item], labels, predicate, max_ahead: int = 2) -> Optional[Tuple[Item, str]]:
        for i, it in enumerate(items):
            if not _has_label(it["text"], labels):
                continue
            # Value on the same line after the label, e.g. "UPI Ref No: 4291...".
            res = predicate(it, True)
            if res:
                return it, res
            for nxt in items[i + 1:i + 1 + max_ahead]:
                res = predicate(nxt, False)
                if res:
                    return nxt, res
        return None

    def extract_all(self, items: List[Item], img_height: int, img_width: int) -> ExtractedData:
        app = self.identify_payment_app(items)
        document_type = "history_list" if looks_like_history_list(items) else "transaction_detail"
        status_bar_cut = img_height * 0.05
        # Only a clock-like line up there is the phone's status bar; a cropped screenshot starts with content.
        body = [i for i in items if i["bbox"]["y"] > status_bar_cut or not parse_clock(i["text"])
                or parse_datetime(i["text"])]

        # Status bar clock
        sb = None
        for it in items:
            if it["bbox"]["y"] <= status_bar_cut and parse_clock(it["text"]):
                sb = self._field(it, it["text"])
                break

        # Amount: the largest money-looking text in the upper half of the screen.
        best = None
        for it in body:
            if it["bbox"]["y"] > img_height * 0.55 or ":" in it["text"] or "%" in it["text"]:
                continue
            m = AMOUNT_RE.match(it["text"].replace(" ", ""))
            if not m:
                continue
            num = m.group("num").replace(",", "")
            if len(num.split(".")[0]) > 7:
                continue
            val = float(num)
            if not (1 <= val <= 1_000_000):
                continue
            score = it["bbox"]["height"] * it["confidence"] * (1.4 if m.group("cur") else 1.0)
            if not best or score > best[0]:
                best = (score, it, f"{val:.2f}")
        if not best:
            # Amount printed on the payee's line ("COMMON SERVICE CENTRE ₹8,375", OCR may read ₹ as ?), or
            # lower down next to the debit account, as PhonePe does.
            for it in body:
                text = it["text"].replace(" ", "")
                m = TRAILING_AMOUNT_RE.search(text) if it["bbox"]["y"] <= img_height * 0.55 else None
                standalone = AMOUNT_RE.match(text) if ":" not in text and "%" not in text else None
                cand = m.group("num") if m else (standalone.group("num") if standalone and "," in text else None)
                if not cand:
                    continue
                val = float(cand.replace(",", ""))
                if 1 <= val <= 1_000_000:
                    score = it["bbox"]["height"] * it["confidence"]
                    if not best or score > best[0]:
                        best = (score, it, f"{val:.2f}")
        amount = self._field(best[1], best[2]) if best else self._field(None)

        words = None
        for it in body:
            t = it["text"].lower()
            if ("rupee" in t or "only" in t) and words_to_number(it["text"]) is not None:
                words = self._field(it, it["text"])
                break

        # UTR / reference: digits near a reference label; fall back to any 12-digit number.
        def utr_pred(it: Item, same_line: bool) -> Optional[str]:
            text = it["text"]
            if same_line:
                text = re.split(r"(?i)(?:utr|ref(?:erence)?\.?\s*no\.?|transaction\s*id|txn\s*id|rrn|:)", text)[-1]
            # Lookarounds, not \b: OCR glues buttons onto the number ("440995361349Copy").
            m = re.search(r"(?<![0-9A-Za-z])(T\d{20,23}|\d{6,22})(?!\d)", text.replace(" ", ""))
            return m.group(1) if m else None

        # An explicit "UTR" line wins: it is the number bank SMS quote. App IDs (PhonePe's T...) come next.
        found = self._after_label(body, ("utr",), utr_pred, max_ahead=4) or self._after_label(body, UTR_LABELS, utr_pred, max_ahead=4)
        if found:
            utr = self._field(found[0], found[1], min(1.0, found[0]["confidence"] + 0.05))
        else:
            fallback = None
            for i in body:
                m = re.search(r"(?<!\d)(\d{12})(?!\d)", i["text"].replace(" ", ""))
                if m and not VPA_RE.search(i["text"]):
                    fallback = (i, m.group(1))
                    break
            # Some app versions place the transaction reference away from a recognised label.
            # Keep a PhonePe T-reference rather than reporting that no UTR was found.
            if not fallback:
                fallback = next(((i, m.group(1)) for i in body
                                 for m in [APP_TXN_RE.search(i["text"].replace(" ", ""))] if m), None)
            utr = self._field(fallback[0], fallback[1]) if fallback else self._field(None)

        # Timestamp
        ts = self._field(None)
        for idx, it in enumerate(body):
            if not re.search(r"\d", it["text"]):
                continue  # labels such as "Date & time" carry no value
            # Several app layouts split day/month/year and time into 2-3 OCR boxes. Try a short
            # neighbouring window instead of assuming that one OCR item contains the whole timestamp.
            dt = None
            for end in range(idx + 1, min(len(body), idx + 4) + 1):
                candidate_text = " ".join(row["text"] for row in body[idx:end])
                dt = parse_datetime(candidate_text)
                if dt:
                    break
            if dt:
                window = body[idx:end]
                date_expression = re.compile(
                    r"\b(?:[0-3]?\d(?:st|nd|rd|th)?\s*[A-Za-z]{3,}|"
                    r"[A-Za-z]{3,}\s*[0-3]?\d|[0-3]?\d[/.-][01]?\d[/.-](?:20)?\d{2})\b", re.I)
                anchor = next((row for row in window if date_expression.search(row["text"])), it)
                direct_anchor = next((row for row in window if parse_datetime(row["text"])), None)
                if direct_anchor:
                    anchor = direct_anchor
                ts = self._field(anchor, dt.strftime("%d %b %Y, %I:%M %p"),
                                 min(0.99, max(anchor["confidence"], 0.70)))
                break

        # Receiver: name and VPA below a "Paid to" label, before any "From" label.
        # Paytm and PhonePe print a bare "To" line above the payee.
        to_idx = next((i for i, it in enumerate(body)
                       if _has_label(it["text"], TO_LABELS) or _norm(it["text"]) in ("to", "to:")), None)
        from_idx = next((i for i, it in enumerate(body)
                         if _norm(it["text"]) in ("from", "debitedfrom", "paidby", "sender")
                         or _norm(it["text"]).startswith("from")), None)
        receiver = receiver_vpa = sender = self._field(None)
        if to_idx is not None:
            label_item = body[to_idx]
            label_rest = re.sub(
                r"(?i)^(?:paid\s+to|sent\s+to|paying|transfer\s+to|to:?|payee|received\s+by|"
                r"banking\s+name|bank\s+name|account\s+name|account\s+holder|beneficiary(?:\s+name)?|"
                r"receiver\s+name|payee\s+name|credited\s+to)\s*[:#-]?\s*",
                "", label_item["text"], count=1).strip()
            if _norm(label_item["text"]) in ("to", "to:"):
                label_rest = ""
            # Some providers put the receiver on the same line as the label (e.g. "Banking Name ABC").
            # Extract this first so the next metadata line (UTR / Date & Time) cannot be mistaken for a name.
            if len(label_rest) > 2 and not VPA_RE.search(label_rest) and not _has_label(label_rest, UTR_LABELS):
                receiver = self._field(label_item, label_rest)

            end = from_idx if from_idx is not None and from_idx > to_idx else min(len(body), to_idx + 7)
            window = body[to_idx:end]
            stop_labels = TO_LABELS + FROM_LABELS + UTR_LABELS + NOTE_LABELS + (
                "date & time", "date and time", "amount", "transaction status", "payment status", "more details"
            )
            for j, it in enumerate(window):
                txt = it["text"].strip()
                m = VPA_RE.search(txt.replace(" ", ""))
                if m and not receiver_vpa.value:
                    receiver_vpa = self._field(it, m.group(1).lower())
                elif j > 0 and not receiver.value and not m and not AMOUNT_RE.match(txt.replace(" ", "")):
                    if not _has_label(txt, stop_labels) and not parse_datetime(txt) and not parse_clock(txt):
                        # Avoid copying common status/metadata lines into the beneficiary name field.
                        if _status_kind(txt) == "unknown" and len(txt) <= 80:
                            receiver = self._field(it, txt)
        if not receiver_vpa.value:
            for i, it in enumerate(body):
                if from_idx is not None and i > from_idx:
                    break
                m = VPA_RE.search(it["text"].replace(" ", ""))
                if m:
                    receiver_vpa = self._field(it, m.group(1).lower())
                    break
        if receiver.value:
            trimmed = re.sub(r"\s*(?:₹|rs\.?|\?)\s*\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?$", "", receiver.value, flags=re.I)
            receiver.value = trimmed or receiver.value
        if from_idx is not None and from_idx + 1 < len(body):
            nxt = body[from_idx + 1]
            if not VPA_RE.search(nxt["text"]):
                sender = self._field(nxt, nxt["text"])

        # Status can sit either above or below the amount depending on app/version. Score short,
        # status-like text instead of letting any unrelated failure word anywhere on screen win.
        status = self._field(None)
        status_candidates = []
        for it in body:
            text = it["text"].strip()
            if not text or len(text) > 80 or _has_label(text, TO_LABELS + ("rupees",)):
                continue
            # BHIM can show a secondary badge such as "Paid in 1.86 Seconds" below the amount.
            # It is a timing/animation note, not the primary transaction status. Selecting it creates
            # a false layout-mismatch warning even when the main "Paid" label is above the amount.
            if re.search(r"\bpaid\s+in\s+\d+(?:[.,]\d+)?\s*(?:seconds?|secs?|s)\b", text, re.I):
                continue
            kind = _status_kind(text)
            if kind == "unknown":
                continue
            y = it["bbox"]["y"] / max(img_height, 1)
            # Some apps place the explicit status in the lower detail area; don't discard it solely by y-position.
            if y > 0.96:
                continue
            compact_bonus = 1.0 if len(text) <= 32 else 0.2
            upper_bonus = 0.8 if y <= 0.55 else 0.25
            explicit_bonus = 0.8 if re.search(r"\b(?:payment|transaction)\s+(?:successful|success|failed|pending|completed)\b", text, re.I) else 0.0
            # Prefer a clear short status, near the main receipt content. A negative status is only
            # preferred when it is itself an explicit status line, not just a word in explanatory text.
            score = it["confidence"] * 2 + compact_bonus + upper_bonus + explicit_bonus
            status_candidates.append((score, it, kind))
        if status_candidates:
            _, hit, kind = max(status_candidates, key=lambda row: row[0] + (0.2 if row[2] == "failure" and len(row[1]["text"]) <= 24 else 0))
            status = self._field(hit, hit["text"])

        note_found = self._after_label(body, NOTE_LABELS,
                                       lambda it, same: None if same else (it["text"] if len(it["text"]) > 1 else None),
                                       max_ahead=1)
        note = self._field(note_found[0], note_found[1]) if note_found else self._field(None)

        txn = next(((it, m.group(1)) for it in body for m in [APP_TXN_RE.search(it["text"].replace(" ", ""))] if m), None)
        app_txn_id = self._field(txn[0], txn[1]) if txn else self._field(None)

        return ExtractedData(
            payment_app=app, document_type=document_type, app_txn_id=app_txn_id,
            amount=amount, utr=utr, timestamp=ts, sender=sender, receiver=receiver,
            receiver_upi_id=receiver_vpa, status=status, amount_in_words=words or self._field(None),
            status_bar_time=sb or self._field(None), note=note,
        )


upi_extractor = UPIExtractor()
