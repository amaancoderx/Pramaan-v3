import base64
import binascii
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import get_db
from app.models.merchant import Merchant, utcnow
from app.models.verification import Verification
from app.schemas.verification import (FieldCorrectionRequest, HandledRequest, PublicVerification, SMSMatchRequest,
                                      VerificationResponse)
from app.security import api_error, get_current_merchant, stream_bytes
from app.services import checks
from app.services.pdf_generator import generate_report
from app.services.pipeline import PipelineError

router = APIRouter()

ERROR_RESPONSES = {
    401: {"description": "Missing or invalid credentials"},
    413: {"description": "File larger than 10 MB"},
    415: {"description": "Not a JPG / PNG / WEBP image"},
    422: {"description": "IMAGE_QUALITY_LOW: blurry, tiny or cropped screenshot"},
}


def _raise(e: PipelineError):
    raise api_error(e.status, e.code, e.message)


def _get(db: Session, merchant: Merchant, vid: str) -> Verification:
    v = db.query(Verification).filter(Verification.id == vid, Verification.merchant_id == merchant.id).first()
    if not v:
        raise api_error(404, "NOT_FOUND", "Check not found.")
    return v


async def _read_limited(file: UploadFile) -> bytes:
    limit = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise api_error(413, "FILE_TOO_LARGE", f"The file is larger than {settings.MAX_IMAGE_SIZE_MB} MB.")
    return data


@router.post("/verify/analyze", response_model=VerificationResponse, responses=ERROR_RESPONSES,
             summary="Verify a payment screenshot")
async def analyze(file: UploadFile = File(..., description="Payment screenshot (JPG, PNG or WEBP, max 10 MB)"),
                  order_ref: Optional[str] = Form(None, description="Order reference from an order-bound QR"),
                  check_mode: str = Form("merchant", description="'merchant': paid to me, recently. "
                                         "'authenticity': only whether the screenshot was edited."),
                  merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    """Runs image forensics, payment rules and reuse detection, and returns an explainable verdict.
    A screenshot alone never yields CONFIRMED; use `/verify/{id}/sms` with the bank SMS for that."""
    data = await _read_limited(file)
    try:
        v = await run_in_threadpool(checks.create_check, db, merchant, data, order_ref or None,
                                    check_mode=check_mode)
    except PipelineError as e:
        _raise(e)
    return checks.to_response(v, db)


@router.get("/verify/{vid}", response_model=VerificationResponse)
def get_check(vid: str, merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    return checks.to_response(_get(db, merchant, vid), db)


@router.post("/verify/{vid}/corrections", response_model=VerificationResponse,
             summary="Correct OCR fields and re-score")
def corrections(vid: str, body: FieldCorrectionRequest, merchant: Merchant = Depends(get_current_merchant),
                db: Session = Depends(get_db)):
    v = _get(db, merchant, vid)
    try:
        v = checks.apply_corrections(db, v, merchant, body)
    except PipelineError as e:
        _raise(e)
    return checks.to_response(v, db)


@router.post("/verify/{vid}/sms", response_model=VerificationResponse,
             summary="Confirm against the bank credit SMS (ground truth)")
def match_sms(vid: str, body: SMSMatchRequest, merchant: Merchant = Depends(get_current_merchant),
              db: Session = Depends(get_db)):
    """UTR and amount both matching the merchant's credit SMS upgrades the verdict to CONFIRMED."""
    v = _get(db, merchant, vid)
    image = None
    if body.sms_image_base64:
        raw = body.sms_image_base64.split(",", 1)[-1]
        try:
            image = base64.b64decode(raw, validate=False)
        except (binascii.Error, ValueError):
            raise api_error(415, "NOT_AN_IMAGE", "The SMS screenshot could not be decoded.")
    if not (body.sms_text and body.sms_text.strip()) and not image:
        raise api_error(422, "SMS_UNREADABLE", "Paste the bank SMS text or attach a screenshot of it.")
    try:
        v = checks.apply_sms(db, v, body.sms_text, image)
    except PipelineError as e:
        _raise(e)
    return checks.to_response(v, db)


@router.post("/verify/{vid}/handled", response_model=VerificationResponse, summary="Mark a check as handled")
def mark_handled(vid: str, body: HandledRequest, merchant: Merchant = Depends(get_current_merchant),
                 db: Session = Depends(get_db)):
    v = _get(db, merchant, vid)
    v.handled = body.handled
    v.handled_at = utcnow() if body.handled else None
    db.commit()
    db.refresh(v)
    return checks.to_response(v, db)


@router.get("/verify/{vid}/report", response_class=Response, summary="Download the PDF report",
            responses={200: {"content": {"application/pdf": {}}}})
def report(vid: str, merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    v = _get(db, merchant, vid)
    resp = checks.to_response(v, db)
    img = str(settings.UPLOAD_DIR / v.image_filename) if resp.image_available else None
    heat = str(settings.UPLOAD_DIR / v.heatmap_filename) if resp.heatmap_url else None
    pdf = generate_report(json.loads(resp.model_dump_json()), merchant.name, img, heat)
    return stream_bytes(pdf, "application/pdf",
                        {"Content-Disposition": f'attachment; filename="Pramaan_{v.id}.pdf"'})


@router.get("/public/verify/{vid}", response_model=PublicVerification, tags=["Public"],
            summary="Public record of a check (opened from the report QR)")
def public_verify(vid: str, db: Session = Depends(get_db)):
    v = db.query(Verification).filter(Verification.id == vid).first()
    if not v:
        raise api_error(404, "NOT_FOUND", "No check with this ID.")
    merchant = db.get(Merchant, v.merchant_id)
    gt = json.loads(v.ground_truth) if v.ground_truth else {}
    utr = v.extracted_utr or ""
    return PublicVerification(
        id=v.id, verdict=v.verdict, risk_score=v.risk_score, amount=v.extracted_amount,
        utr_masked=("•" * 8 + utr[-4:]) if len(utr) >= 4 else "Not available", payment_app=v.payment_app,
        checked_at=v.created_at, merchant_name=merchant.name if merchant else "Pramaan merchant",
        ground_truth_status=gt.get("status", "NONE"))
