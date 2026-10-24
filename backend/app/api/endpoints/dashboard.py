from datetime import timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.merchant import Merchant, utcnow
from app.models.verification import Verification
from app.schemas.verification import HistoryItem
from app.security import get_current_merchant

router = APIRouter()

FLAGGED = ("LIKELY FAKE", "SUSPICIOUS")


@router.get("/dashboard/stats")
def stats(merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    q = db.query(Verification).filter(Verification.merchant_id == merchant.id)
    counts = dict(q.with_entities(Verification.verdict, func.count()).group_by(Verification.verdict).all())
    saved = (q.filter(Verification.verdict.in_(FLAGGED))
             .with_entities(func.coalesce(func.sum(Verification.extracted_amount), 0.0)).scalar())
    volume = q.with_entities(func.coalesce(func.sum(Verification.extracted_amount), 0.0)).scalar()

    tz, utc = ZoneInfo(settings.TIMEZONE), ZoneInfo("UTC")
    today = utcnow().replace(tzinfo=utc).astimezone(tz).date()
    start = today - timedelta(days=13)
    days = {start + timedelta(days=i): {"total": 0, "flagged": 0} for i in range(14)}
    since = utcnow() - timedelta(days=15)
    for created, verdict in q.filter(Verification.created_at >= since).with_entities(
            Verification.created_at, Verification.verdict):
        d = created.replace(tzinfo=utc).astimezone(tz).date()
        if d in days:
            days[d]["total"] += 1
            days[d]["flagged"] += int(verdict in FLAGGED)

    return {
        "total_checks": sum(counts.values()),
        "confirmed_count": counts.get("CONFIRMED", 0),
        "likely_genuine_count": counts.get("LIKELY GENUINE", 0),
        "suspicious_count": counts.get("SUSPICIOUS", 0),
        "fake_count": counts.get("LIKELY FAKE", 0),
        "reused_count": q.filter(Verification.is_reused.is_(True)).count(),
        "handled_count": q.filter(Verification.handled.is_(True)).count(),
        "rupees_saved": round(float(saved or 0), 2),
        "total_volume": round(float(volume or 0), 2),
        "trend": [{"date": d.isoformat(), **v} for d, v in days.items()],
    }


@router.get("/dashboard/history")
def history(
    search: Optional[str] = Query(None, max_length=40, description="UTR or check ID (partial match)"),
    verdict: Optional[Literal["CONFIRMED", "LIKELY GENUINE", "SUSPICIOUS", "LIKELY FAKE"]] = None,
    app: Optional[str] = Query(None, max_length=20),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db),
):
    q = db.query(Verification).filter(Verification.merchant_id == merchant.id)
    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(Verification.extracted_utr.ilike(term) | Verification.id.ilike(term))
    if verdict:
        q = q.filter(Verification.verdict == verdict)
    if app:
        q = q.filter(Verification.payment_app == app)
    total = q.count()
    rows = q.order_by(desc(Verification.created_at)).offset(offset).limit(limit).all()
    items = [HistoryItem(id=r.id, verdict=r.verdict, risk_score=r.risk_score, amount=r.extracted_amount,
                         utr=r.extracted_utr, payment_app=r.payment_app, is_reused=r.is_reused, handled=r.handled,
                         created_at=r.created_at,
                         image_available=bool(r.image_filename) and (settings.UPLOAD_DIR / r.image_filename).exists())
             for r in rows]
    return {"total": total, "limit": limit, "offset": offset, "items": items}
