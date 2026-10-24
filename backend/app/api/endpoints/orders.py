from typing import Literal, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.merchant import Merchant
from app.models.verification import Order
from app.schemas.verification import GenerateQRRequest
from app.security import api_error, get_current_merchant
from app.services.qr_generator import new_order_ref, qr_data_url, upi_uri

router = APIRouter()


def _out(o: Order, m: Merchant) -> dict:
    return {"order_ref": o.order_ref, "amount": o.amount, "status": o.status, "upi_uri": o.upi_uri,
            "qr_image_data_url": qr_data_url(o.upi_uri), "merchant_upi_id": m.registered_upi_id,
            "merchant_name": m.name, "created_at": o.created_at, "verification_id": o.verification_id}


@router.post("/qr/generate", summary="Create an order-bound UPI QR")
def generate(body: GenerateQRRequest, merchant: Merchant = Depends(get_current_merchant),
             db: Session = Depends(get_db)):
    """The order reference is embedded in the UPI deep link note (`tn`). A screenshot checked against this order
    must show the reference (or at least the amount), otherwise it is flagged."""
    ref = (body.note or "").strip().upper() or new_order_ref()
    if db.query(Order).filter(Order.order_ref == ref).first():
        raise api_error(409, "ORDER_EXISTS", f"Reference {ref} is already used. Leave it blank for a new one.")
    o = Order(order_ref=ref, merchant_id=merchant.id, amount=round(body.amount, 2),
              upi_uri=upi_uri(merchant.registered_upi_id, merchant.name, body.amount, ref))
    db.add(o)
    db.commit()
    db.refresh(o)
    return _out(o, merchant)


@router.get("/qr/orders", summary="List order-bound QRs")
def list_orders(status: Optional[Literal["open", "paid"]] = None, merchant: Merchant = Depends(get_current_merchant),
                db: Session = Depends(get_db)):
    q = db.query(Order).filter(Order.merchant_id == merchant.id)
    if status:
        q = q.filter(Order.status == status)
    return {"items": [_out(o, merchant) for o in q.order_by(desc(Order.created_at)).limit(50).all()]}
