from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base
from app.models.merchant import utcnow


class Verification(Base):
    __tablename__ = "verifications"

    id = Column(String, primary_key=True, index=True)  # PRM-XXXXXXXX
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)

    # Files are stored under random names; they are deleted after RETENTION_HOURS.
    image_filename = Column(String, nullable=True)
    heatmap_filename = Column(String, nullable=True)
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    image_purged_at = Column(DateTime, nullable=True)

    verdict = Column(String, nullable=False, index=True)
    risk_score = Column(Float, default=0.0)
    final_verdict_reason = Column(Text, nullable=True)
    strictness = Column(String, default="standard")

    payment_app = Column(String, default="generic", index=True)
    extracted_amount = Column(Float, nullable=True)
    extracted_utr = Column(String, nullable=True, index=True)
    extracted_timestamp = Column(String, nullable=True)
    extracted_receiver_upi = Column(String, nullable=True)

    # JSON payloads
    extracted_data = Column(Text, nullable=True)      # ExtractedData (current, incl. corrections)
    ocr_text = Column(Text, nullable=True)            # masked full OCR text
    corrections = Column(Text, nullable=True)
    rule_reasons = Column(Text, nullable=True)        # re-computed on correction
    forensic_reasons = Column(Text, nullable=True)    # computed once from pixels
    duplicate_reason = Column(Text, nullable=True)
    order_reasons = Column(Text, nullable=True)
    ground_truth = Column(Text, nullable=True)
    passed_checks = Column(Text, nullable=True)
    forensic_summary = Column(Text, nullable=True)

    order_ref = Column(String, nullable=True, index=True)
    perceptual_hash = Column(String, nullable=True, index=True)
    is_reused = Column(Boolean, default=False)
    reused_first_seen_id = Column(String, nullable=True)

    handled = Column(Boolean, default=False)
    handled_at = Column(DateTime, nullable=True)

    processing_time_seconds = Column(Float, default=0.0)
    created_at = Column(DateTime, default=utcnow, index=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class DuplicateHash(Base):
    """Fingerprint index kept after images are purged, so reuse is still detected later."""

    __tablename__ = "duplicate_hashes"

    id = Column(Integer, primary_key=True, index=True)
    phash = Column(String, index=True, nullable=False)
    dhash = Column(String, nullable=True)
    utr = Column(String, index=True, nullable=True)
    amount = Column(Float, nullable=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True)
    verification_id = Column(String, ForeignKey("verifications.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utcnow)


class Order(Base):
    """Order-bound UPI QR: the reference is put in the `tn` note of the deep link."""

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    order_ref = Column(String, unique=True, index=True, nullable=False)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    upi_uri = Column(Text, nullable=False)
    status = Column(String, default="open")  # open | paid
    verification_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)
