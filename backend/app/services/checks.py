"""Persisted verification checks: create, re-score after corrections / SMS, and serialise for the API."""
import json
import re
import secrets
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.merchant import Merchant, utcnow
from app.models.verification import Order, Verification
from app.schemas.rules import PassedCheck, ReasonDetail
from app.schemas.verification import (ExtractedData, FieldCorrectionRequest, GroundTruth, LayerScores, OrderBinding,
                                      ReusedFirstSeen, VerificationResponse)
from app.services import duplicate_detector, sms_parser
from app.services.extractor import parse_datetime
from app.services.ocr_engine import ocr_engine
from app.services.pipeline import (MerchantProfile, PipelineError, analyze_image, compose_verdict, dumps,
                                   loads_passed, loads_reasons, rescore_rules)
from app.services.rules_engine import rules_engine

_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_check_id() -> str:
    return "PRM-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))


def profile(m: Merchant, check_mode: str = "merchant") -> MerchantProfile:
    return MerchantProfile(m.name, m.registered_upi_id, m.allowed_window_minutes, m.strictness, check_mode,
                           m.registered_receiver_name or "")


def mode_of(v: Verification) -> str:
    try:
        return json.loads(v.forensic_summary or "{}").get("check_mode", "merchant")
    except ValueError:
        return "merchant"


def _ext_for(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def _norm_ref(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def order_reasons(order: Order, ocr_text: str, amount: Optional[str]) -> Tuple[List[ReasonDetail], List[PassedCheck], str]:
    P = rules_engine.penalties
    ref_seen = _norm_ref(order.order_ref) in _norm_ref(ocr_text)
    try:
        amt = float(amount) if amount else None
    except ValueError:
        amt = None
    amount_ok = amt is not None and abs(amt - order.amount) < 0.01
    reasons: List[ReasonDetail] = []
    passed: List[PassedCheck] = []
    if ref_seen:
        passed.append(PassedCheck(code="R_ORDER_REF_FOUND", layer="rules",
                                  title=f"Order reference {order.order_ref} is on the receipt"))
        matched_by = "reference"
    elif amount_ok:
        matched_by = "amount"
        reasons.append(ReasonDetail(
            code="R_ORDER_REF_MISSING", severity="MEDIUM", layer="rules", title="Order reference not visible",
            message=f"The amount matches order {order.order_ref}, but the reference from your QR is not on the "
                    "receipt. The customer may have paid without scanning your order QR.",
            penalty=P["order_amount_only"], evidence_type="order", field="note"))
    else:
        matched_by = "none"
        reasons.append(ReasonDetail(
            code="R_ORDER_REF_MISSING", severity="CRITICAL", layer="rules", title="Not a payment for this order",
            message=f"Neither the order reference {order.order_ref} nor the order amount ₹{order.amount:,.2f} "
                    "appears on this receipt. It is proof of some other payment.",
            penalty=P["order_ref_missing"], evidence_type="order", field="note"))
    if ref_seen and amt is not None and not amount_ok:
        reasons.append(ReasonDetail(
            code="R_ORDER_AMOUNT_MISMATCH", severity="CRITICAL", layer="rules", title="Amount differs from the order",
            message=f"Order {order.order_ref} is for ₹{order.amount:,.2f}, but the receipt shows ₹{amt:,.2f}.",
            penalty=P["order_ref_missing"], evidence_type="field", field="amount"))
    return reasons, passed, matched_by


def _ground_truth_reason(gt: Dict[str, Any]) -> Optional[ReasonDetail]:
    if not gt or gt.get("status") != "SMS_MISMATCH":
        return None
    return ReasonDetail(code=gt["code"], severity=gt["severity"], layer="ground_truth", title=gt["title"],
                        message=gt["message"], penalty=gt["penalty"], evidence_type="sms",
                        evidence_value={k: gt.get(k) for k in ("sms_amount", "sms_utr", "bank")})


def recompute(v: Verification) -> None:
    gt = json.loads(v.ground_truth) if v.ground_truth else {}
    reasons = loads_reasons(v.rule_reasons) + loads_reasons(v.forensic_reasons) + loads_reasons(v.order_reasons)
    if v.duplicate_reason:
        reasons.append(ReasonDetail(**json.loads(v.duplicate_reason)))
    gtr = _ground_truth_reason(gt)
    if gtr:
        reasons.append(gtr)
    res = compose_verdict(reasons, v.strictness, sms_matched=gt.get("status") == "SMS_MATCHED",
                          check_mode=mode_of(v))
    v.verdict, v.risk_score, v.final_verdict_reason = res.verdict, res.risk_score, res.final_reason
    if gt.get("status") == "SMS_MATCHED" and any(r.code == "DUP_UTR_REUSED" for r in reasons):
        v.final_verdict_reason = ("The SMS matches, but this UTR was already used for an earlier check, so this "
                                  "credit has already been counted. " + res.final_reason)


def create_check(db: Session, merchant: Merchant, data: bytes, order_ref: Optional[str] = None,
                 now: Optional[datetime] = None, created_at: Optional[datetime] = None,
                 check_mode: str = "merchant") -> Verification:
    check_mode = "authenticity" if check_mode == "authenticity" else "merchant"
    order = None
    if order_ref:
        order = db.query(Order).filter(Order.order_ref == order_ref.strip().upper(),
                                       Order.merchant_id == merchant.id).first()
        if not order:
            raise PipelineError(404, "NOT_FOUND", f"Order {order_ref} was not found.")

    vid = new_check_id()
    token = secrets.token_hex(16)
    heatmap_name = f"{token}_ela.jpg"
    a = analyze_image(data, profile(merchant, check_mode), now=now, heatmap_path=str(settings.UPLOAD_DIR / heatmap_name))

    image_name = token + _ext_for(data)
    (settings.UPLOAD_DIR / image_name).write_bytes(data)
    ex = a.extracted
    amount = float(ex.amount.value) if ex.amount.value else None
    ocr_text = sms_parser.mask_sensitive("\n".join(i["text"] for i in a.ocr_items))

    phash, dhash = duplicate_detector.fingerprint(a.image, ex)
    dup, first = duplicate_detector.find_reuse(db, merchant_id=merchant.id, verification_id=vid,
                                               utr=ex.utr.value, amount=amount, phash=phash, dhash=dhash)
    dup = duplicate_detector.classify(dup, first, check_mode=check_mode)
    passed = a.rule_passed + a.forensic_passed
    if not dup:
        passed.append(PassedCheck(code="DUP_NONE", layer="duplicate", title="Not seen in any earlier check"))

    o_reasons: List[ReasonDetail] = []
    if order:
        o_reasons, o_passed, matched_by = order_reasons(order, ocr_text, ex.amount.value)
        passed += o_passed

    v = Verification(
        id=vid, merchant_id=merchant.id, image_filename=image_name,
        heatmap_filename=heatmap_name if a.heatmap_path else None, image_width=a.width, image_height=a.height,
        strictness=merchant.strictness, payment_app=ex.payment_app, extracted_amount=amount,
        extracted_utr=ex.utr.value, extracted_timestamp=ex.timestamp.value,
        extracted_receiver_upi=ex.receiver_upi_id.value, extracted_data=ex.model_dump_json(), ocr_text=ocr_text,
        rule_reasons=dumps(a.rule_reasons), forensic_reasons=dumps(a.forensic_reasons),
        order_reasons=dumps(o_reasons), duplicate_reason=dup.model_dump_json() if dup else None,
        passed_checks=dumps(passed), forensic_summary=json.dumps({**a.forensic_summary, "check_mode": check_mode}),
        order_ref=order.order_ref if order else None, perceptual_hash=f"{phash}:{dhash}", is_reused=bool(dup and dup.penalty > 0),
        reused_first_seen_id=first.id if first else None,
        processing_time_seconds=round(a.timings["total"], 2),
    )
    if created_at:
        v.created_at = v.updated_at = created_at
    recompute(v)
    db.add(v)
    db.flush()
    duplicate_detector.register(db, merchant_id=merchant.id, verification_id=vid, utr=ex.utr.value, amount=amount,
                                phash=phash, dhash=dhash)
    if order and order.status == "open" and v.verdict != "LIKELY FAKE" and o_reasons == []:
        order.status, order.verification_id = "paid", vid
    db.commit()
    db.refresh(v)
    return v


def apply_corrections(db: Session, v: Verification, merchant: Merchant, c: FieldCorrectionRequest) -> Verification:
    ex = ExtractedData.model_validate_json(v.extracted_data)
    changes = c.model_dump(exclude_unset=True)
    for name, value in changes.items():
        f = getattr(ex, name)
        value = (value or "").strip() or None
        if name == "amount" and value:
            cleaned = re.sub(r"[^\d.]", "", value)
            try:
                value = f"{float(cleaned):.2f}"
            except ValueError:
                raise PipelineError(422, "INVALID_FIELD", f"'{value}' is not a valid amount.")
        if name == "utr" and value:
            value = re.sub(r"\s", "", value)
        if name == "timestamp" and value:
            dt = parse_datetime(value)
            if not dt:
                raise PipelineError(422, "INVALID_FIELD", "Write the date like '23 Oct 2026, 2:45 PM'.")
            value = dt.strftime("%d %b %Y, %I:%M %p")
        f.value, f.confidence, f.corrected = value, 1.0 if value else 0.0, True

    created_local = None
    if v.created_at:
        from zoneinfo import ZoneInfo
        created_local = v.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)
    rule_reasons, rule_passed = rescore_rules(ex, profile(merchant, mode_of(v)), v.image_width or 0, v.image_height or 0,
                                              now=created_local)
    v.extracted_data = ex.model_dump_json()
    v.extracted_amount = float(ex.amount.value) if ex.amount.value else None
    v.extracted_utr, v.extracted_timestamp = ex.utr.value, ex.timestamp.value
    v.extracted_receiver_upi = ex.receiver_upi_id.value
    v.rule_reasons = dumps(rule_reasons)
    v.corrections = json.dumps({**(json.loads(v.corrections) if v.corrections else {}), **changes})

    passed = [p for p in loads_passed(v.passed_checks) if p.layer != "rules"] + rule_passed
    if v.order_ref:
        order = db.query(Order).filter(Order.order_ref == v.order_ref).first()
        if order:
            o_reasons, o_passed, _ = order_reasons(order, v.ocr_text or "", ex.amount.value)
            v.order_reasons = dumps(o_reasons)
            passed += o_passed

    if "utr" in changes or "amount" in changes:
        phash, dhash = (v.perceptual_hash or ":").split(":")
        dup, first = duplicate_detector.find_reuse(db, merchant_id=merchant.id, verification_id=v.id,
                                                   utr=ex.utr.value, amount=v.extracted_amount,
                                                   phash=phash or "0" * 16, dhash=dhash or "0" * 16)
        dup = duplicate_detector.classify(dup, first, check_mode=mode_of(v), now=v.created_at)
        v.duplicate_reason = dup.model_dump_json() if dup else None
        v.is_reused = bool(dup and dup.penalty > 0)
        v.reused_first_seen_id = first.id if first else None
        passed = [p for p in passed if p.layer != "duplicate"]
        if not dup:
            passed.append(PassedCheck(code="DUP_NONE", layer="duplicate", title="Not seen in any earlier check"))

    if v.ground_truth:
        gt = json.loads(v.ground_truth)
        if gt.get("sms"):
            gt.update(sms_parser.match(gt["sms"], v.extracted_amount, v.extracted_utr))
            v.ground_truth = json.dumps(gt)
    v.passed_checks = dumps(passed)
    recompute(v)
    db.commit()
    db.refresh(v)
    return v


def apply_sms(db: Session, v: Verification, sms_text: Optional[str], sms_image: Optional[bytes]) -> Verification:
    text = sms_text or ""
    if sms_image:
        from app.services.pipeline import decode_image
        img = decode_image(sms_image)
        text = (text + "\n" + " ".join(i["text"] for i in ocr_engine.extract(img))).strip()
    parsed = sms_parser.parse_sms(text)
    if not parsed["parsed"]:
        raise PipelineError(422, "SMS_UNREADABLE",
                            "No amount or 12-digit UPI reference was found in that SMS. Paste the full message "
                            "from your bank.")
    result = sms_parser.match(parsed, v.extracted_amount, v.extracted_utr)
    gt = {**result, "sms_amount": parsed["amount"], "sms_utr": parsed["utr"], "bank": parsed["bank"],
          "account_masked": parsed["account_masked"], "sms": parsed,
          "sms_text_masked": sms_parser.mask_sensitive(text)[:1000], "matched_at": utcnow().isoformat() + "Z"}
    v.ground_truth = json.dumps(gt)
    passed = [p for p in loads_passed(v.passed_checks) if p.layer != "ground_truth"]
    if result["status"] == "SMS_MATCHED":
        passed.append(PassedCheck(code="GT_SMS_MATCHED", layer="ground_truth", title=result["title"]))
    v.passed_checks = dumps(passed)
    recompute(v)
    if v.verdict == "CONFIRMED" and v.order_ref:
        order = db.query(Order).filter(Order.order_ref == v.order_ref).first()
        if order:
            order.status, order.verification_id = "paid", v.id
    db.commit()
    db.refresh(v)
    return v


def to_response(v: Verification, db: Session) -> VerificationResponse:
    ex = ExtractedData.model_validate_json(v.extracted_data) if v.extracted_data else ExtractedData()
    gt = json.loads(v.ground_truth) if v.ground_truth else {}
    reasons = loads_reasons(v.rule_reasons) + loads_reasons(v.forensic_reasons) + loads_reasons(v.order_reasons)
    if v.duplicate_reason:
        reasons.append(ReasonDetail(**json.loads(v.duplicate_reason)))
    gtr = _ground_truth_reason(gt)
    if gtr:
        reasons.append(gtr)
    comp = compose_verdict(reasons, v.strictness, sms_matched=gt.get("status") == "SMS_MATCHED",
                           check_mode=mode_of(v))

    order = None
    if v.order_ref:
        o_reasons = loads_reasons(v.order_reasons)
        matched_by = ("reference" if not o_reasons or all(r.code == "R_ORDER_AMOUNT_MISMATCH" for r in o_reasons)
                      else "amount" if any(r.severity == "MEDIUM" for r in o_reasons) else "none")
        row = db.query(Order).filter(Order.order_ref == v.order_ref).first()
        if row:
            order = OrderBinding(order_ref=row.order_ref, amount=row.amount, status=row.status, matched_by=matched_by)

    first = None
    if v.duplicate_reason:
        ev = json.loads(v.duplicate_reason).get("evidence_value") or {}
        if ev.get("first_seen_at"):
            first = ReusedFirstSeen(id=ev.get("first_seen_id") or "", seen_at=ev["first_seen_at"].rstrip("Z"),
                                    same_merchant=bool(ev.get("same_merchant")))

    available = bool(v.image_filename) and (settings.UPLOAD_DIR / v.image_filename).exists()
    heat_ok = available and bool(v.heatmap_filename) and (settings.UPLOAD_DIR / v.heatmap_filename).exists()
    return VerificationResponse(
        id=v.id, verdict=v.verdict, risk_score=v.risk_score, final_verdict_reason=v.final_verdict_reason or "",
        reasons=comp.reasons, passed_checks=loads_passed(v.passed_checks), payment_app=v.payment_app,
        image_url=f"/api/storage/uploads/{v.image_filename}" if available else None,
        heatmap_url=f"/api/storage/uploads/{v.heatmap_filename}" if heat_ok else None,
        image_available=available, image_width=v.image_width, image_height=v.image_height,
        report_url=f"/api/verify/{v.id}/report", extracted_data=ex, is_reused=v.is_reused,
        reused_first_seen=first,
        ground_truth=GroundTruth(**{k: gt.get(k) for k in GroundTruth.model_fields if k in gt}) if gt else GroundTruth(),
        order=order, layer_scores=LayerScores(**comp.layer_scores), strictness=v.strictness,
        check_mode=mode_of(v), handled=v.handled,
        handled_at=v.handled_at, created_at=v.created_at, processing_time_seconds=v.processing_time_seconds or 0.0,
    )
