from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.config import new_api_key
from app.database import get_db
from app.models.merchant import Merchant
from app.schemas.merchant import MerchantLogin, MerchantRegister, MerchantResponse, MerchantUpdate, Token
from app.security import api_error, create_access_token, get_current_merchant, hash_password, verify_password

router = APIRouter()


def _token(m: Merchant) -> Token:
    return Token(access_token=create_access_token(m), merchant=MerchantResponse.model_validate(m))


@router.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(body: MerchantRegister, db: Session = Depends(get_db)):
    if db.query(Merchant).filter(Merchant.email == body.email).first():
        raise api_error(409, "EMAIL_TAKEN", "An account with this email already exists. Sign in instead.")
    m = Merchant(email=body.email, password_hash=hash_password(body.password), name=body.name.strip(),
                 registered_upi_id=body.registered_upi_id,
                 registered_receiver_name=(body.registered_receiver_name or body.name).strip(), api_key=new_api_key())
    db.add(m)
    db.commit()
    db.refresh(m)
    return _token(m)


@router.post("/auth/login", response_model=Token)
def login(body: MerchantLogin, db: Session = Depends(get_db)):
    m = db.query(Merchant).filter(Merchant.email == body.email.strip().lower()).first()
    if not m or not verify_password(body.password, m.password_hash):
        raise api_error(401, "UNAUTHORIZED", "Wrong email or password.")
    return _token(m)


@router.get("/auth/me", response_model=MerchantResponse)
def me(merchant: Merchant = Depends(get_current_merchant)):
    return merchant


@router.get("/settings", response_model=MerchantResponse)
def get_settings(merchant: Merchant = Depends(get_current_merchant)):
    return merchant


@router.put("/settings", response_model=MerchantResponse)
def update_settings(body: MerchantUpdate, merchant: Merchant = Depends(get_current_merchant),
                    db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(merchant, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    db.refresh(merchant)
    return merchant


@router.post("/settings/api-key/rotate", response_model=MerchantResponse)
def rotate_api_key(merchant: Merchant = Depends(get_current_merchant), db: Session = Depends(get_db)):
    merchant.api_key = new_api_key()
    db.commit()
    db.refresh(merchant)
    return merchant
