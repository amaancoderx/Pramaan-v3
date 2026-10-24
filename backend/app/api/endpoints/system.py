import json
import random
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.merchant import Merchant, utcnow
from app.models.verification import Verification
from app.security import api_error, get_current_merchant, stream_bytes
from app.services.mock_receipts import DEMO_SAMPLES, crop_and_recompress, render_demo
from app.services.ocr_engine import ocr_engine
from app.services.pipeline import local_now
from app.services.rules_engine import rules_engine

router = APIRouter()

BENCHMARK_SNAPSHOT = Path(__file__).resolve().parents[2] / "assets" / "benchmark_results.json"


@router.get("/health", tags=["Public"])
def health():
    return {"status": "ok", "version": settings.PROJECT_VERSION, "ocr_engine": ocr_engine.name,
            "time": utcnow().isoformat() + "Z"}


@router.get("/rules", tags=["Public"], summary="The active rules.yaml")
def rules():
    return rules_engine.rules


@router.get("/benchmark/results", tags=["Public"], summary="Synthetic benchmark results")
def benchmark():
    # A locally re-run evaluation wins over the snapshot committed with the code.
    for path in (settings.BENCHMARK_PATH, BENCHMARK_SNAPSHOT):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "pending", "message": "Run: python scripts/evaluate_benchmark.py"}


MEDIA = {".png": "image/png", ".jpg": "image/jpeg"}


@router.get("/demo/samples", tags=["Demo"], summary="Mock test receipts")
def demo_list(merchant: Merchant = Depends(get_current_merchant)):
    return {"items": [{"key": k, "label": label, "description": desc, "expected": exp}
                      for k, (label, desc, exp) in DEMO_SAMPLES.items()]}


@router.get("/demo/samples/{key}", tags=["Demo"], response_class=Response,
            summary="Render a mock receipt for the signed-in merchant")
def demo_sample(key: str, merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    if key not in DEMO_SAMPLES:
        raise api_error(404, "NOT_FOUND", "Unknown sample.")
    if key == "reused":
        last = (db.query(Verification)
                .filter(Verification.merchant_id == merchant.id, Verification.image_filename.isnot(None),
                        Verification.is_reused.is_(False), Verification.verdict.in_(["LIKELY GENUINE", "CONFIRMED"]))
                .order_by(desc(Verification.created_at)).first())
        path = settings.UPLOAD_DIR / last.image_filename if last and last.image_filename else None
        if not path or not path.exists():
            raise api_error(404, "NOT_FOUND", "Check the 'Unedited receipt' sample first, then try this one.")
        data, ext = crop_and_recompress(path.read_bytes())
    else:
        data, ext = render_demo(key, local_now(), merchant.name, merchant.registered_upi_id, random.Random())
    return stream_bytes(data, MEDIA[ext],
                        {"Content-Disposition": f'inline; filename="mock_{key}{ext}"', "Cache-Control": "no-store"})
