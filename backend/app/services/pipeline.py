"""The verification pipeline: image -> OCR -> (forensics, rules) -> verdict. Shared by the API, the benchmark
evaluator and the demo seeder, so all three produce identical results."""
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import cv2
import numpy as np

from app.config import settings
from app.schemas.rules import SEVERITY_RANK, PassedCheck, ReasonDetail
from app.schemas.verification import ExtractedData
from app.services.extractor import upi_extractor
from app.services.forensics import forensic_engine
from app.services.ocr_engine import ocr_engine
from app.services.rules_engine import MERCHANT_ONLY_CODES, RuleContext, rules_engine


class PipelineError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class MerchantProfile:
    name: str
    upi_id: str
    allowed_window_minutes: int = 60
    strictness: str = "standard"
    check_mode: str = "merchant"
    receiver_name: str = ""


def local_now() -> datetime:
    return datetime.now(ZoneInfo(settings.TIMEZONE)).replace(tzinfo=None)


def decode_image(data: bytes) -> np.ndarray:
    if len(data) > settings.MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise PipelineError(413, "FILE_TOO_LARGE", f"The file is larger than {settings.MAX_IMAGE_SIZE_MB} MB.")
    if len(data) < 100:
        raise PipelineError(415, "NOT_AN_IMAGE", "The file is empty or not an image.")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise PipelineError(415, "NOT_AN_IMAGE",
                            "This file is not a JPG, PNG or WEBP image. HEIC photos must be converted first.")
    return img


def header_color(img: np.ndarray) -> Tuple[int, int, int]:
    h = img.shape[0]
    b, g, r = cv2.mean(img[int(h * 0.04):int(h * 0.10), :])[:3]
    return int(r), int(g), int(b)


@dataclass
class ImageAnalysis:
    extracted: ExtractedData
    ocr_items: List[Dict[str, Any]]
    rule_reasons: List[ReasonDetail]
    rule_passed: List[PassedCheck]
    forensic_reasons: List[ReasonDetail]
    forensic_passed: List[PassedCheck]
    forensic_summary: Dict[str, Any]
    heatmap_path: Optional[str]
    width: int
    height: int
    header_rgb: Tuple[int, int, int]
    image: np.ndarray
    timings: Dict[str, float]


def analyze_image(data: bytes, merchant: MerchantProfile, now: Optional[datetime] = None,
                  heatmap_path: Optional[str] = None) -> ImageAnalysis:
    t0 = time.perf_counter()
    img = decode_image(data)
    ok, msg = ocr_engine.check_image_quality(img)
    if not ok:
        raise PipelineError(422, "IMAGE_QUALITY_LOW", msg or "Image quality too low.")
    h, w = img.shape[:2]

    t1 = time.perf_counter()
    items = ocr_engine.extract(img)
    t2 = time.perf_counter()
    extracted = upi_extractor.extract_all(items, h, w)
    if len(items) < 4 or (not extracted.amount.value and not extracted.utr.value):
        raise PipelineError(422, "IMAGE_QUALITY_LOW",
                            "Image quality too low: no payment amount or reference number could be read. The "
                            "screenshot may be cropped, blurred, or not a payment receipt.")

    hdr = header_color(img)
    rules = rules_engine.evaluate(extracted, _rule_context(merchant, now, w, h, hdr))
    _apply_validity(extracted, rules.extracted_fields_validity)
    t3 = time.perf_counter()
    forensic = forensic_engine.analyze(data, img, extracted, items, heatmap_path)
    t4 = time.perf_counter()
    return ImageAnalysis(
        extracted=extracted, ocr_items=items, rule_reasons=rules.violations, rule_passed=rules.passed,
        forensic_reasons=forensic["reasons"], forensic_passed=forensic["passed"],
        forensic_summary=forensic["summary"], heatmap_path=forensic["heatmap_path"], width=w, height=h,
        header_rgb=hdr, image=img,
        timings={"decode": t1 - t0, "ocr": t2 - t1, "rules": t3 - t2, "forensics": t4 - t3, "total": t4 - t0},
    )


def _rule_context(merchant: MerchantProfile, now: Optional[datetime], w: int = 0, h: int = 0,
                  hdr: Optional[Tuple[int, int, int]] = None) -> RuleContext:
    return RuleContext(merchant_upi_id=merchant.upi_id, merchant_name=merchant.name,
                       allowed_window_minutes=merchant.allowed_window_minutes, now=now or local_now(),
                       img_width=w, img_height=h, header_rgb=hdr, check_mode=merchant.check_mode,
                       merchant_receiver_name=merchant.receiver_name)


def _apply_validity(extracted: ExtractedData, validity: Dict[str, bool]) -> None:
    for name, valid in validity.items():
        if hasattr(extracted, name):
            getattr(extracted, name).is_valid = valid


def rescore_rules(extracted: ExtractedData, merchant: MerchantProfile, w: int, h: int,
                  now: Optional[datetime] = None) -> Tuple[List[ReasonDetail], List[PassedCheck]]:
    for name in ExtractedData.model_fields:
        f = getattr(extracted, name, None)
        if hasattr(f, "is_valid"):
            f.is_valid = bool(f.value)
    res = rules_engine.evaluate(extracted, _rule_context(merchant, now, w, h))
    _apply_validity(extracted, res.extracted_fields_validity)
    return res.violations, res.passed


# Forensic signals are heuristic (especially across real app versions); they should raise caution but
# never produce a 100/100 verdict by themselves.
LAYER_CAPS = {"rules": 100.0, "forensics": 45.0, "duplicate": 50.0, "ground_truth": 50.0}

VERDICT_TEXT = {
    "CONFIRMED": "Your bank SMS matches this payment's UTR and amount. You can hand over goods.",
    "LIKELY GENUINE": "No problems found, but a screenshot alone is not proof. Check your bank SMS or soundbox "
                      "before handing over goods.",
    "SUSPICIOUS": "Do not hand over goods yet. Confirm in your bank app.",
    "LIKELY FAKE": "Do not hand over goods. Confirm in your bank app.",
}

# Editing check: the question is whether the screenshot was altered, not whether it paid this shop.
AUTHENTICITY_TEXT = {
    **VERDICT_TEXT,
    "LIKELY GENUINE": "No signs of editing found. The screenshot looks like an unaltered receipt from a payment "
                      "app. Only a bank SMS or statement proves the money moved.",
    "SUSPICIOUS": "Some signs of editing. Treat this screenshot with caution.",
    "LIKELY FAKE": "This screenshot shows clear signs of editing or is not a valid payment.",
}


@dataclass
class Verdict:
    verdict: str
    risk_score: float
    final_reason: str
    reasons: List[ReasonDetail]
    layer_scores: Dict[str, float]


def compose_verdict(reasons: List[ReasonDetail], strictness: str, sms_matched: bool = False,
                    check_mode: str = "merchant") -> Verdict:
    texts = AUTHENTICITY_TEXT if check_mode == "authenticity" else VERDICT_TEXT
    ranked = sorted(reasons, key=lambda r: (SEVERITY_RANK.get(r.severity, 0), r.penalty), reverse=True)
    layers = {k: 0.0 for k in LAYER_CAPS}
    for r in ranked:
        layers[r.layer] = layers.get(r.layer, 0.0) + r.penalty
    layers = {k: round(min(LAYER_CAPS.get(k, 100.0), v), 1) for k, v in layers.items()}
    score = round(min(100.0, sum(layers.values())), 1)
    th = rules_engine.thresholds(strictness)
    # These checks answer whether a receipt is safe to accept for this merchant, not whether its pixels
    # were forged. Keep their penalties in the operational risk score, but do not let them alone label a
    # perfectly genuine screenshot as fabricated.
    context_codes = MERCHANT_ONLY_CODES if check_mode == "merchant" else set()
    context_penalty = sum(r.penalty for r in ranked if r.code in context_codes)
    # Avoid stacking uncertain OCR/reference warnings on top of correlated pixel heuristics until the
    # fake threshold is crossed. These signals still raise the displayed risk and can make the result SUSPICIOUS.
    non_definitive_codes = context_codes | {
        "R_UTR_FORMAT_INVALID", "R_TXN_FUTURE", "R_TXN_ID_TIME_MISMATCH", "R_TIMESTAMP_MISSING",
        "R_STATUS_MISSING", "R_STATUS_NOT_SUCCESS", "R_LOW_CONFIDENCE", "R_LAYOUT_MISMATCH",
        "R_CLOCK_INCONSISTENCY", "R_HISTORY_LIST_SCREEN", "R_AMT_MISSING", "R_UTR_MISSING",
        "R_RECEIVER_NOT_VISIBLE", "R_TIMESTAMP_MISSING", "R_STATUS_MISSING", "R_AMT_INVALID",
    }
    non_definitive_penalty = layers["forensics"] + sum(
        r.penalty for r in ranked if r.layer != "forensics" and r.code in non_definitive_codes)
    forgery_score = max(0.0, score - non_definitive_penalty)
    # A screenshot that clearly says Failed/Pending may be a genuine screenshot of an unsuccessful payment.
    # That makes it unsafe to accept, but does not by itself prove image forgery. Only independent, more
    # definitive contradictions should force the LIKELY FAKE label.
    blocking = [r for r in ranked if r.severity == "CRITICAL" and r.code not in non_definitive_codes]
    reused_utr = any(r.code == "DUP_UTR_REUSED" for r in ranked)
    history_view = check_mode == "merchant" and any(r.code == "R_HISTORY_LIST_SCREEN" for r in ranked)

    if sms_matched and not reused_utr:
        verdict, score = "CONFIRMED", 0.0
    elif blocking or forgery_score >= th["fake_at"]:
        verdict = "LIKELY FAKE"
    elif history_view or score >= th["suspicious_at"] or context_penalty > 0:
        verdict = "SUSPICIOUS"
    else:
        verdict = "LIKELY GENUINE"

    problems = [r for r in ranked if r.penalty > 0 and r.layer != "ground_truth" or r.severity == "CRITICAL"]
    if verdict == "CONFIRMED":
        text = texts["CONFIRMED"]
        if problems:
            text += " Note: the screenshot itself has issues listed below; keep this report."
    elif problems:
        top = "; ".join(r.title for r in problems[:2])
        text = f"{top}. {texts[verdict]}"
    else:
        text = texts[verdict]
    return Verdict(verdict=verdict, risk_score=score, final_reason=text, reasons=ranked, layer_scores=layers)


def dumps(models: List[Any]) -> str:
    return json.dumps([m.model_dump(mode="json") for m in models])


def loads_reasons(s: Optional[str]) -> List[ReasonDetail]:
    return [ReasonDetail(**r) for r in json.loads(s)] if s else []


def loads_passed(s: Optional[str]) -> List[PassedCheck]:
    return [PassedCheck(**p) for p in json.loads(s)] if s else []
