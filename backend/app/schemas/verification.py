from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.rules import BoundingBox, PassedCheck, ReasonDetail

Verdict = Literal["CONFIRMED", "LIKELY GENUINE", "SUSPICIOUS", "LIKELY FAKE"]


class ExtractedField(BaseModel):
    value: Optional[str] = None
    confidence: float = 0.0
    bbox: Optional[BoundingBox] = None
    is_valid: bool = True
    corrected: bool = False


class ExtractedData(BaseModel):
    payment_app: str = "generic"
    document_type: Literal["transaction_detail", "history_list", "unknown"] = "unknown"
    amount: ExtractedField = Field(default_factory=ExtractedField)
    utr: ExtractedField = Field(default_factory=ExtractedField)
    timestamp: ExtractedField = Field(default_factory=ExtractedField)
    sender: ExtractedField = Field(default_factory=ExtractedField)
    receiver: ExtractedField = Field(default_factory=ExtractedField)
    receiver_upi_id: ExtractedField = Field(default_factory=ExtractedField)
    status: ExtractedField = Field(default_factory=ExtractedField)
    amount_in_words: ExtractedField = Field(default_factory=ExtractedField)
    status_bar_time: ExtractedField = Field(default_factory=ExtractedField)
    note: ExtractedField = Field(default_factory=ExtractedField)
    # App's own transaction ID (PhonePe: T + yyMMddHHmm...), used to cross-check the shown date.
    app_txn_id: ExtractedField = Field(default_factory=ExtractedField)


class FieldCorrectionRequest(BaseModel):
    amount: Optional[str] = None
    utr: Optional[str] = None
    timestamp: Optional[str] = None
    receiver: Optional[str] = None
    receiver_upi_id: Optional[str] = None
    status: Optional[str] = None


class GroundTruth(BaseModel):
    status: Literal["NONE", "SMS_MATCHED", "SMS_MISMATCH"] = "NONE"
    sms_amount: Optional[float] = None
    sms_utr: Optional[str] = None
    bank: Optional[str] = None
    account_masked: Optional[str] = None
    amount_matched: Optional[bool] = None
    utr_matched: Optional[bool] = None
    message: Optional[str] = None


class ReusedFirstSeen(BaseModel):
    id: str
    seen_at: datetime
    same_merchant: bool


class OrderBinding(BaseModel):
    order_ref: str
    amount: float
    status: str
    matched_by: Literal["reference", "amount", "none"]


class LayerScores(BaseModel):
    forensics: float = 0.0
    rules: float = 0.0
    ground_truth: float = 0.0
    duplicate: float = 0.0


class VerificationResponse(BaseModel):
    id: str
    verdict: Verdict
    risk_score: float
    final_verdict_reason: str
    reasons: List[ReasonDetail]
    passed_checks: List[PassedCheck]
    payment_app: str
    image_url: Optional[str]
    heatmap_url: Optional[str]
    image_available: bool
    image_width: Optional[int]
    image_height: Optional[int]
    report_url: str
    extracted_data: ExtractedData
    is_reused: bool
    reused_first_seen: Optional[ReusedFirstSeen]
    ground_truth: GroundTruth
    order: Optional[OrderBinding]
    layer_scores: LayerScores
    strictness: str
    check_mode: str = "merchant"
    handled: bool
    handled_at: Optional[datetime]
    created_at: datetime
    processing_time_seconds: float


class SMSMatchRequest(BaseModel):
    sms_text: Optional[str] = Field(default=None, max_length=2000)
    sms_image_base64: Optional[str] = Field(default=None, description="Screenshot of the bank SMS / notification, base64 or data URL")


class HandledRequest(BaseModel):
    handled: bool = True


class GenerateQRRequest(BaseModel):
    amount: float = Field(gt=0, le=200000)
    note: Optional[str] = Field(default=None, max_length=30, pattern=r"^[A-Za-z0-9\-]*$")


class PublicVerification(BaseModel):
    id: str
    verdict: Verdict
    risk_score: float
    amount: Optional[float]
    utr_masked: str
    payment_app: str
    checked_at: datetime
    merchant_name: str
    ground_truth_status: str


class HistoryItem(BaseModel):
    id: str
    verdict: Verdict
    risk_score: float
    amount: Optional[float]
    utr: Optional[str]
    payment_app: str
    is_reused: bool
    handled: bool
    created_at: datetime
    image_available: bool


