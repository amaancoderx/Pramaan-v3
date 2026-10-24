from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    registered_upi_id = Column(String, nullable=False)
    registered_receiver_name = Column(String(100), nullable=True)
    allowed_window_minutes = Column(Integer, default=60, nullable=False)
    strictness = Column(String, default="standard", nullable=False)  # lenient | standard | strict
    api_key = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
