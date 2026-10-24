from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Security, status
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.merchant import Merchant

bearer_scheme = HTTPBearer(auto_error=False, description="JWT from /api/auth/login")
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False, description="Merchant API key (Settings page)")


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(merchant: Merchant) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(merchant.id), "email": merchant.email, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_merchant(
    bearer: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_scheme),
    db: Session = Depends(get_db),
) -> Merchant:
    if api_key:
        merchant = db.query(Merchant).filter(Merchant.api_key == api_key.strip()).first()
        if merchant:
            return merchant
        raise api_error(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", "Invalid API key.")

    if bearer and bearer.credentials:
        try:
            payload = jwt.decode(bearer.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            merchant_id = int(payload.get("sub", 0))
        except (JWTError, ValueError):
            raise api_error(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", "Session expired. Please sign in again.")
        merchant = db.get(Merchant, merchant_id)
        if merchant:
            return merchant

    raise api_error(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", "Sign in or provide an X-API-Key header.")


def stream_bytes(data: bytes, media_type: str, headers: dict) -> StreamingResponse:
    """Large in-memory bodies are streamed in chunks: a single big write through the Next.js dev proxy on
    a reused connection can be cut off mid-body."""
    def chunks():
        for i in range(0, len(data), 32768):
            yield data[i:i + 32768]
    return StreamingResponse(chunks(), media_type=media_type, headers={**headers, "Content-Length": str(len(data))})
