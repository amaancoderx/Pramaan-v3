"""Demo merchant and a lived-in history, produced by running real mock receipts through the real pipeline."""
import logging
import random
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.models.merchant import Merchant, utcnow
from app.models.verification import Order, Verification
from app.security import hash_password
from app.services import checks
from app.services.mock_receipts import TAMPERS, encode, random_spec, render_receipt
from app.services.pipeline import PipelineError
from app.services.qr_generator import new_order_ref, upi_uri
from app.services.retention import purge_expired

log = logging.getLogger("pramaan.seed")

# (kind, weight). "clean_sms" receipts are later confirmed with a matching bank SMS.
MIX = [("clean", 7), ("clean_sms", 6), ("edited_amount", 2), ("pasted_receiver", 2), ("edited_utr", 1),
       ("edited_date", 1), ("editor_software", 1), ("heavy_compression", 1), ("reuse", 1)]


def ensure_demo_merchant(db: Session) -> Merchant:
    m = db.query(Merchant).filter(Merchant.email == settings.DEMO_MERCHANT_EMAIL).first()
    if not m:
        m = Merchant(email=settings.DEMO_MERCHANT_EMAIL, password_hash=hash_password(settings.DEMO_MERCHANT_PASSWORD),
                     name=settings.DEMO_MERCHANT_NAME, registered_upi_id=settings.DEMO_MERCHANT_UPI_ID,
                     registered_receiver_name=settings.DEMO_MERCHANT_NAME, api_key=settings.DEMO_MERCHANT_API_KEY, allowed_window_minutes=60, strictness="standard")
        db.add(m)
        db.commit()
        db.refresh(m)
        log.info("created demo merchant %s", m.email)
    elif not m.registered_receiver_name:
        m.registered_receiver_name = m.name
        db.commit()
        db.refresh(m)
    return m


def seed_history(db: Session, merchant: Merchant, count: int = 24, seed: int = 7) -> int:
    if db.query(Verification).filter(Verification.merchant_id == merchant.id).count():
        return 0
    rng = random.Random(seed)
    tz, utc = ZoneInfo(settings.TIMEZONE), ZoneInfo("UTC")
    kinds = [k for k, w in MIX for _ in range(w)]
    rng.shuffle(kinds)
    kinds = (kinds * 3)[:count]
    made, last_clean = 0, None
    for i, kind in enumerate(kinds):
        # Six checks in the last day (images still on disk), the rest spread over two weeks.
        hours_ago = rng.uniform(0.3, 20) if i < 6 else rng.uniform(26, 13 * 24)
        created = utcnow() - timedelta(hours=hours_ago)
        local = created.replace(tzinfo=utc).astimezone(tz).replace(tzinfo=None)
        if kind == "reuse" and last_clean:
            data = last_clean
        else:
            r = render_receipt(random_spec(rng, local, merchant.registered_receiver_name or merchant.name, merchant.registered_upi_id))
            if kind.startswith("clean") or kind == "reuse":
                data, _ = encode(r.image)
                last_clean = data
            else:
                _, data, _ = TAMPERS[kind](r, rng, local)
        try:
            v = checks.create_check(db, merchant, data, now=local, created_at=created)
        except PipelineError as e:
            log.warning("seed sample %d skipped: %s", i, e.message)
            continue
        if kind == "clean_sms" and v.extracted_utr and v.extracted_amount:
            sms = (f"Dear Customer, INR {v.extracted_amount:,.2f} credited to A/c XX4821 on {local:%d-%m-%y} by "
                   f"UPI Ref No {v.extracted_utr}. Avl Bal INR 48,210.55 - HDFC Bank")
            checks.apply_sms(db, v, sms, None)
        if v.verdict != "LIKELY GENUINE" and rng.random() < 0.6:
            v.handled, v.handled_at = True, created + timedelta(minutes=rng.randint(2, 30))
            db.commit()
        made += 1

    for amt in (640.0, 1890.0):
        ref = new_order_ref()
        db.add(Order(order_ref=ref, merchant_id=merchant.id, amount=amt,
                     upi_uri=upi_uri(merchant.registered_upi_id, merchant.name, amt, ref)))
    db.commit()
    purge_expired(db)
    log.info("seeded %d demo checks", made)
    return made
