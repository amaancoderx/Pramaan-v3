from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
Layer = Literal["forensics", "rules", "ground_truth", "duplicate"]

SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class ReasonDetail(BaseModel):
    code: str
    severity: Severity
    layer: Layer = "rules"
    title: str
    message: str
    field: Optional[str] = None
    penalty: float = 0.0
    evidence_type: Optional[str] = None  # heatmap | field | metadata | sms | duplicate | order
    evidence_value: Optional[Any] = None
    region: Optional[BoundingBox] = None


class PassedCheck(BaseModel):
    code: str
    layer: Layer
    title: str


class RuleEvaluationResult(BaseModel):
    risk_score: float
    violations: List[ReasonDetail] = Field(default_factory=list)
    passed: List[PassedCheck] = Field(default_factory=list)
    extracted_fields_validity: Dict[str, bool] = Field(default_factory=dict)
