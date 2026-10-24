"""Reused-proof detection: the same UTR, or the same screenshot (even cropped or re-compressed), seen before."""
from datetime import datetime, timedelta
from typing import Optional, Tuple

import cv2
import imagehash
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.models.verification import DuplicateHash, Verification
from app.schemas.rules import ReasonDetail
from app.schemas.verification import ExtractedData

# Hamming distances on 256-bit hashes of the payment-specific fields.
SAME_IMAGE_MAX_DIST = 26       # measured: reused copies 12-18, different payments >= 34
SAME_AMOUNT_MAX_DIST = 32      # looser, only when the amounts match and a UTR is unreadable
# The same shop checking the same proof again this soon, before handing over goods, is re-checking one sale.
RECHECK_WINDOW = timedelta(minutes=30)

# Fields that differ between two genuine payments but survive cropping and re-compression. The UTR is left out
# on purpose so a reused screenshot with an edited UTR still matches.
FINGERPRINT_FIELDS = ("amount", "timestamp", "sender", "receiver_upi_id")


def content_region(img: np.ndarray, ex: ExtractedData) -> np.ndarray:
    """Stack normalised crops of the payment-specific fields into one small image."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = gray.shape
    strips = []
    for name in FINGERPRINT_FIELDS:
        b = getattr(ex, name).bbox
        if not b:
            continue
        crop = gray[max(0, b.y):min(h, b.y + b.height), max(0, b.x):min(w, b.x + b.width)]
        if crop.size:
            strips.append(cv2.resize(crop, (256, 32), interpolation=cv2.INTER_AREA))
    if len(strips) >= 2:
        return np.vstack(strips)
    return cv2.resize(gray[int(h * 0.08):int(h * 0.9), :], (256, 512), interpolation=cv2.INTER_AREA)


def fingerprint(img: np.ndarray, ex: ExtractedData) -> Tuple[str, str]:
    pil = Image.fromarray(content_region(img, ex))
    return str(imagehash.phash(pil, hash_size=16)), str(imagehash.dhash(pil, hash_size=16))


def _reason(code: str, title: str, message: str, first: Verification, same_merchant: bool, extra: dict) -> ReasonDetail:
    return ReasonDetail(code=code, severity="CRITICAL", layer="duplicate", title=title, message=message,
                        field="utr" if code == "DUP_UTR_REUSED" else None, penalty=50.0, evidence_type="duplicate",
                        evidence_value={"first_seen_id": first.id if same_merchant else None,
                                        "first_seen_at": first.created_at.isoformat() + "Z",
                                        "same_merchant": same_merchant, **extra})


def _when(v: Verification) -> str:
    return v.created_at.strftime("%d %b %Y, %H:%M UTC")


def classify(reason: Optional[ReasonDetail], first: Optional[Verification], *, check_mode: str = "merchant",
             now: Optional[datetime] = None) -> Optional[ReasonDetail]:
    """Turn a match into reuse (risk) or information.

    Reuse fraud is a proof coming back for a new purchase or at another shop. A shopkeeper checking the same
    proof again minutes later, before handing over goods, is one sale checked twice. And in the editing check
    the question is whether the image was altered, which a repeat says nothing about."""
    if not reason or not first:
        return reason
    same = bool((reason.evidence_value or {}).get("same_merchant"))
    now = now or datetime.utcnow()
    recheck = same and not first.handled and now - first.created_at <= RECHECK_WINDOW
    if recheck:
        return reason.model_copy(update={
            "code": "DUP_RECHECK", "severity": "INFO", "penalty": 0.0, "title": "You checked this payment before",
            "message": f"You already checked this payment at {_when(first)} ({first.id}). If this is the same sale, "
                       "this is just a re-check. If the customer is using it for a new purchase, it is a reused "
                       "proof: do not accept it."})
    if check_mode == "authenticity":
        return reason.model_copy(update={
            "severity": "INFO", "penalty": 0.0,
            "message": reason.message.rsplit(". ", 1)[0].rstrip(".") + ". Shown for information: this check looks "
                       "for editing; a repeat says nothing about whether the image was altered."})
    return reason


def find_reuse(db: Session, *, merchant_id: int, verification_id: str, utr: Optional[str], amount: Optional[float],
               phash: str, dhash: str) -> Tuple[Optional[ReasonDetail], Optional[Verification]]:
    if utr and len(utr) >= 10:
        first = (db.query(Verification)
                 .filter(Verification.extracted_utr == utr, Verification.id != verification_id)
                 .order_by(Verification.created_at.asc()).first())
        if first:
            same = first.merchant_id == merchant_id
            where = f"in your check {first.id}" if same else "at another shop using Pramaan"
            return _reason("DUP_UTR_REUSED", "This UTR was already used",
                           f"UTR {utr} was already presented on {_when(first)} {where}. One payment cannot be "
                           "used twice. This is a reused proof.", first, same, {"utr": utr}), first

    cur_p, cur_d = imagehash.hex_to_hash(phash), imagehash.hex_to_hash(dhash)
    rows = (db.query(DuplicateHash).filter(DuplicateHash.verification_id != verification_id)
            .order_by(DuplicateHash.created_at.desc()).limit(5000).all())
    best: Optional[Tuple[int, DuplicateHash]] = None
    for row in rows:
        try:
            dist = max(cur_p - imagehash.hex_to_hash(row.phash),
                       cur_d - imagehash.hex_to_hash(row.dhash) if row.dhash else 0)
        except Exception:
            continue
        same_amount = amount is not None and row.amount is not None and abs(amount - row.amount) < 0.01
        utr_unknown = not utr or not row.utr
        if dist <= SAME_IMAGE_MAX_DIST or (same_amount and utr_unknown and dist <= SAME_AMOUNT_MAX_DIST):
            if best is None or dist < best[0]:
                best = (dist, row)
    if best:
        first = db.get(Verification, best[1].verification_id)
        if first:
            same = first.merchant_id == merchant_id
            similarity = round(100 - best[0] / 64 * 100, 1)
            where = f"in your check {first.id}" if same else "at another shop using Pramaan"
            return _reason("DUP_IMAGE_REUSED", "Same screenshot seen before",
                           f"This screenshot matches one checked on {_when(first)} {where} ({similarity}% similar), "
                           "even after cropping or compression. It is a reused proof.", first, same,
                           {"similarity": similarity}), first
    return None, None


def register(db: Session, *, merchant_id: int, verification_id: str, utr: Optional[str], amount: Optional[float],
             phash: str, dhash: str) -> None:
    db.add(DuplicateHash(phash=phash, dhash=dhash, utr=utr, amount=amount, merchant_id=merchant_id,
                         verification_id=verification_id))
