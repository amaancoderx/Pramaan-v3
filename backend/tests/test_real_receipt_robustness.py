from datetime import datetime

from app.schemas.rules import ReasonDetail
from app.schemas.verification import ExtractedData, ExtractedField
from app.services.extractor import upi_extractor
from app.services.pipeline import compose_verdict
from app.services.rules_engine import RuleContext, rules_engine


def item(text, y, x=100, confidence=0.98):
    return {"text": text, "confidence": confidence,
            "bbox": {"x": x, "y": y, "width": max(40, len(text) * 10), "height": 30}}


def test_phonepe_can_be_identified_from_t_reference_when_logo_is_not_ocr_readable():
    ref = "T2610231420123456789012"
    items = [item("Payment successful", 100), item("₹ 750", 280), item(ref, 900),
             item("23 Oct 2026, 02:20 PM", 1100)]
    ex = upi_extractor.extract_all(items, img_height=2000, img_width=900)
    assert ex.payment_app == "phonepe"
    assert ex.utr.value == ref
    assert ex.app_txn_id.value == ref


def test_unrecognised_reference_format_is_a_warning_not_automatic_proof_of_forgery():
    ex = ExtractedData(
        payment_app="generic",
        amount=ExtractedField(value="750.00", confidence=0.98),
        utr=ExtractedField(value="4291827364511", confidence=0.98),
        timestamp=ExtractedField(value="23 Oct 2026, 02:20 PM", confidence=0.98),
        receiver_upi_id=ExtractedField(value="shop@okaxis", confidence=0.98),
        status=ExtractedField(value="Payment successful", confidence=0.98),
    )
    result = rules_engine.evaluate(ex, RuleContext(
        merchant_upi_id="shop@okaxis", merchant_name="Shop", allowed_window_minutes=60,
        now=datetime(2026, 10, 23, 14, 30),
    ))
    reason = next(r for r in result.violations if r.code == "R_UTR_FORMAT_INVALID")
    assert reason.severity == "HIGH"
    assert compose_verdict(result.violations, "standard").verdict == "SUSPICIOUS"


def test_visual_forensics_alone_cannot_fill_the_fake_threshold():
    finding = ReasonDetail(code="F_TEST", severity="HIGH", layer="forensics", title="Pixel anomaly",
                           message="The image contains a visual anomaly.", penalty=100.0)
    result = compose_verdict([finding], "standard", check_mode="authenticity")
    assert result.risk_score == 45.0
    assert result.verdict == "SUSPICIOUS"


def test_payment_to_another_upi_is_not_mislabeled_as_a_forged_image():
    ex = ExtractedData(
        payment_app="paytm",
        amount=ExtractedField(value="750.00", confidence=0.98),
        utr=ExtractedField(value="429182736451", confidence=0.98),
        timestamp=ExtractedField(value="23 Oct 2026, 02:20 PM", confidence=0.98),
        receiver_upi_id=ExtractedField(value="someoneelse@ybl", confidence=0.98),
        status=ExtractedField(value="Payment successful", confidence=0.98),
    )
    result = rules_engine.evaluate(ex, RuleContext(
        merchant_upi_id="shop@okaxis", merchant_name="Shop", allowed_window_minutes=60,
        now=datetime(2026, 10, 23, 14, 30),
    ))
    verdict = compose_verdict(result.violations, "standard", check_mode="merchant")
    assert verdict.verdict == "SUSPICIOUS"
    assert verdict.risk_score >= 50


def test_uncertain_ocr_and_pixel_signals_combined_stay_suspicious():
    reasons = [
        ReasonDetail(code="R_UTR_FORMAT_INVALID", severity="HIGH", layer="rules",
                     title="Reference format warning", message="Reference format could not be verified.", penalty=25),
        ReasonDetail(code="F_TEXT_REGION_INCONSISTENT", severity="HIGH", layer="forensics",
                     title="Text appearance differs", message="A pixel-based heuristic differed.", penalty=70),
    ]
    result = compose_verdict(reasons, "standard", check_mode="authenticity")
    assert result.risk_score == 70.0
    assert result.verdict == "SUSPICIOUS"


def test_strong_amount_contradiction_still_returns_likely_fake():
    reason = ReasonDetail(code="R_AMT_WORDS_MISMATCH", severity="CRITICAL", layer="rules",
                          title="Amount mismatch", message="Amount in words differs from digits.", penalty=45)
    assert compose_verdict([reason], "standard", check_mode="authenticity").verdict == "LIKELY FAKE"


def test_low_confidence_amount_words_mismatch_is_only_a_warning():
    ex = ExtractedData(
        payment_app="generic",
        amount=ExtractedField(value="750.00", confidence=0.52),
        amount_in_words=ExtractedField(value="Rupees Eight Hundred Only", confidence=0.48),
        utr=ExtractedField(value="429182736451", confidence=0.98),
        timestamp=ExtractedField(value="23 Oct 2026, 02:20 PM", confidence=0.98),
        receiver_upi_id=ExtractedField(value="shop@okaxis", confidence=0.98),
        status=ExtractedField(value="Payment successful", confidence=0.98),
    )
    result = rules_engine.evaluate(ex, RuleContext(
        merchant_upi_id="shop@okaxis", merchant_name="Shop", allowed_window_minutes=60,
        now=datetime(2026, 10, 23, 14, 30),
    ))
    reason = next(r for r in result.violations if r.code == "R_AMT_WORDS_MISMATCH")
    assert reason.severity == "HIGH"
    assert compose_verdict(result.violations, "standard").verdict != "LIKELY FAKE"


def test_non_success_status_and_repeated_ui_pattern_do_not_force_fake_verdict():
    reasons = [
        ReasonDetail(code="R_STATUS_NOT_SUCCESS", severity="HIGH", layer="rules",
                     title="Payment is not marked successful", message="Status could not be confirmed.", penalty=50),
        ReasonDetail(code="F_COPY_MOVE", severity="MEDIUM", layer="forensics",
                     title="Repeated image pattern found", message="UI repeats visual elements.", penalty=3),
    ]
    result = compose_verdict(reasons, "standard", check_mode="merchant")
    assert result.verdict == "SUSPICIOUS"
    assert result.risk_score == 53.0


def test_status_extractor_finds_paid_below_the_header():
    items = [item("BHIM - Bharat's Own Payments App", 220), item("Paid", 620), item("₹8,450.00", 670),
             item("UTR 150842972422", 1180), item("23 Oct 2026, 02:20 PM", 1240)]
    ex = upi_extractor.extract_all(items, img_height=1800, img_width=900)
    assert ex.status.value == "Paid"
    result = rules_engine.evaluate(ex, RuleContext(
        merchant_upi_id="shop@okhdfcbank", merchant_name="Shop", allowed_window_minutes=600,
        now=datetime(2026, 10, 23, 15, 0),
    ))
    assert "R_STATUS_NOT_SUCCESS" not in {r.code for r in result.violations}


def test_banking_name_same_line_is_receiver_not_the_next_metadata_label():
    items = [
        item("BHIM - Bharat's Own Payments App", 220),
        item("Paid", 620),
        item("₹ 8,450.00", 670),
        item("Banking Name AHASAN ZAFAR", 1000),
        item("UTR / Reference No.", 1100),
        item("150842972422", 1140),
        item("Date & Time", 1100, x=300),
        item("23rd Oct 26, 03:08 pm", 1140, x=300),
    ]
    ex = upi_extractor.extract_all(items, img_height=1800, img_width=900)
    assert ex.payment_app == "bhim"
    assert ex.status.value == "Paid"
    assert ex.receiver.value == "AHASAN ZAFAR"
    assert ex.utr.value == "150842972422"
    assert ex.timestamp.value == "23 Oct 2026, 03:08 PM"
    assert ex.timestamp.bbox is not None and ex.timestamp.bbox.x >= 250


def test_banking_name_on_following_line_is_receiver():
    items = [
        item("Paytm", 100), item("Paid", 250), item("₹400.00", 300),
        item("Banking Name", 600), item("TEST RECEIVER", 640),
        item("UTR / Reference No.", 720), item("432198765432", 760),
        item("Date & Time", 820, x=300), item("23rd Oct 26, 03:08 pm", 860, x=300),
    ]
    ex = upi_extractor.extract_all(items, img_height=1000, img_width=600)
    assert ex.payment_app == "paytm"
    assert ex.receiver.value == "TEST RECEIVER"
    assert ex.utr.value == "432198765432"
    assert ex.timestamp.value == "23 Oct 2026, 03:08 PM"


def test_fampay_and_famapp_brand_names_are_detected():
    assert upi_extractor.identify_payment_app([item("FamPay", 100)]) == "fampay"
    assert upi_extractor.identify_payment_app([item("FamApp", 100)]) == "fampay"
    # The older FamPay receipt design often prominently says FamCoins instead of repeating the brand.
    assert upi_extractor.identify_payment_app([item("You earned 780 FamCoins", 500)]) == "fampay"


def test_paytm_history_screenshot_is_detected_as_history_not_single_receipt():
    from app.services.extractor import looks_like_history_list
    items = [
        item("Paytm Balance & History", 100),
        item("Yesterday Paid to Shop One", 300), item("-₹120.00", 330),
        item("Yesterday Paid to Shop Two", 420), item("-₹250.00", 450),
        item("Today Payment received", 540), item("+₹700.00", 570),
    ]
    assert looks_like_history_list(items)
    ex = upi_extractor.extract_all(items, img_height=1000, img_width=600)
    assert ex.document_type == "history_list"


def test_history_screen_warning_cannot_by_itself_mark_image_fake():
    ex = ExtractedData(document_type="history_list")
    context = RuleContext(merchant_upi_id="shop@okaxis", merchant_name="Shop", allowed_window_minutes=60,
                          now=datetime(2026, 10, 23, 14, 30))
    res = rules_engine.evaluate(ex, context)
    assert {reason.code for reason in res.violations} == {"R_HISTORY_LIST_SCREEN"}
    assert compose_verdict(res.violations, "standard").verdict == "SUSPICIOUS"


def test_status_near_lower_receipt_details_is_not_discarded_by_position_alone():
    items = [item("Paytm", 100), item("₹400.00", 300), item("Paid", 900)]
    ex = upi_extractor.extract_all(items, img_height=1000, img_width=600)
    assert ex.status.value == "Paid"


def test_cred_app_name_does_not_match_the_word_credited():
    assert upi_extractor.identify_payment_app([item("Payment credited successfully", 100)]) == "generic"


def test_bhim_timing_badge_does_not_override_primary_paid_status_or_layout():
    items = [
        item("BHIM - Bharat's Own Payments App", 220),
        item("Paid", 620),
        item("₹8,450.00", 670, x=400),
        item("Paid in 1.86 Seconds", 780),
        item("Banking Name AHASAN ZAFAR", 1000),
        item("UTR / Reference No.", 1100), item("150842972422", 1140),
        item("Date & Time", 1100, x=300), item("23rd Oct 26, 03:08 pm", 1140, x=300),
    ]
    ex = upi_extractor.extract_all(items, img_height=1800, img_width=900)
    assert ex.status.value == "Paid"
    context = RuleContext(merchant_upi_id="shop@okhdfcbank", merchant_name="Shop",
                          allowed_window_minutes=600, now=datetime(2026, 10, 23, 15, 15),
                          img_width=900, img_height=1800, merchant_receiver_name="AHASAN ZAFAR")
    result = rules_engine.evaluate(ex, context)
    assert "R_LAYOUT_MISMATCH" not in {r.code for r in result.violations}


def test_older_fampay_receipt_layout_extracts_paid_to_date_and_upi_reference():
    items = [
        item("FamCoins", 100), item("₹780.0", 260),
        item("Paid to RAZORPAY SOFTWARE PVT L", 340),
        item("10 Mar 2021 at 08:46 am", 400),
        item("UPI Transaction ID 302916903363", 600),
        item("Transaction ID FMPIB5213097", 640),
    ]
    ex = upi_extractor.extract_all(items, img_height=900, img_width=450)
    assert ex.payment_app == "fampay"
    assert ex.amount.value == "780.00"
    assert ex.receiver.value == "RAZORPAY SOFTWARE PVT L"
    assert ex.timestamp.value == "10 Mar 2021, 08:46 AM"
    assert ex.utr.value == "302916903363"
