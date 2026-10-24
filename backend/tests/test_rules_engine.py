from datetime import datetime

import pytest

from app.schemas.verification import ExtractedData, ExtractedField
from app.services.extractor import parse_datetime, words_to_number
from app.services.pipeline import compose_verdict
from app.services.rules_engine import RuleContext, is_dummy_utr, rules_engine

NOW = datetime(2026, 10, 23, 14, 30)
UPI = "sharmakirana@okhdfcbank"


def ctx(**kw) -> RuleContext:
    base = dict(merchant_upi_id=UPI, merchant_name="Sharma Kirana Store", allowed_window_minutes=60, now=NOW)
    base.update(kw)
    return RuleContext(**base)


def receipt(**fields) -> ExtractedData:
    values = {
        "amount": "750.00", "utr": "429182736451", "timestamp": "23 Oct 2026, 02:20 PM",
        "receiver_upi_id": UPI, "status": "Payment successful",
        "amount_in_words": "Rupees Seven Hundred Fifty Only", "status_bar_time": "14:24",
    }
    values.update(fields)
    return ExtractedData(payment_app="generic", **{
        k: ExtractedField(value=v, confidence=0.97) if v is not None else ExtractedField() for k, v in values.items()})


def codes(result):
    return {r.code for r in result.violations}


def test_clean_receipt_has_no_violations():
    res = rules_engine.evaluate(receipt(), ctx())
    assert res.violations == []
    assert res.risk_score == 0
    assert {"R_UTR_FORMAT", "R_RECEIVER_MATCH", "R_TXN_WINDOW", "R_AMT_WORDS_MATCH"} <= {p.code for p in res.passed}


def test_receiver_mismatch_is_critical():
    res = rules_engine.evaluate(receipt(receiver_upi_id="fraudster@ybl"), ctx())
    r = next(r for r in res.violations if r.code == "R_RECEIVER_MISMATCH")
    assert r.severity == "CRITICAL" and r.field == "receiver_upi_id"
    # A receiver mismatch means this payment is not for the configured merchant; it does not by itself
    # prove the receipt image was forged.
    assert compose_verdict(res.violations, "standard").verdict == "SUSPICIOUS"


def test_amount_words_mismatch():
    res = rules_engine.evaluate(receipt(amount="7500.00"), ctx())
    assert "R_AMT_WORDS_MISMATCH" in codes(res)


@pytest.mark.parametrize("utr,code", [
    ("42918273645", "R_UTR_FORMAT_INVALID"),
    ("4291827364511", "R_UTR_FORMAT_INVALID"),
    ("111111111111", "R_UTR_DUMMY_SEQUENCE"),
    ("123456789012", "R_UTR_DUMMY_SEQUENCE"),
    (None, "R_UTR_MISSING"),
])
def test_utr_rules(utr, code):
    assert code in codes(rules_engine.evaluate(receipt(utr=utr), ctx()))


def test_phonepe_transaction_id_format_allowed():
    ex = receipt(utr="T2610231420123456789012")
    ex.payment_app = "phonepe"
    assert not {"R_UTR_FORMAT_INVALID", "R_UTR_DUMMY_SEQUENCE"} & codes(rules_engine.evaluate(ex, ctx()))


def test_future_transaction_time():
    res = rules_engine.evaluate(receipt(timestamp="25 Oct 2026, 02:20 PM"), ctx())
    assert "R_TXN_FUTURE" in codes(res)


def test_transaction_outside_allowed_window():
    res = rules_engine.evaluate(receipt(timestamp="20 Oct 2026, 02:20 PM", status_bar_time="14:21"), ctx())
    assert "R_TXN_EXPIRED" in codes(res)
    # A merchant with a 7-day window accepts the same receipt.
    res = rules_engine.evaluate(receipt(timestamp="20 Oct 2026, 02:20 PM", status_bar_time="14:21"),
                                ctx(allowed_window_minutes=7 * 24 * 60))
    assert "R_TXN_EXPIRED" not in codes(res)


def test_status_bar_clock_before_payment():
    res = rules_engine.evaluate(receipt(timestamp="23 Oct 2026, 02:25 PM", status_bar_time="13:40"), ctx())
    assert "R_CLOCK_INCONSISTENCY" in codes(res)


def test_status_bar_clock_twelve_hour_is_fine():
    res = rules_engine.evaluate(receipt(status_bar_time="2:24"), ctx())
    assert "R_CLOCK_INCONSISTENCY" not in codes(res)


def test_bhim_paid_status_is_a_success_status():
    ex = receipt(status="Paid")
    ex.payment_app = "bhim"
    res = rules_engine.evaluate(ex, ctx())
    assert "R_STATUS_NOT_SUCCESS" not in codes(res)
    assert "R_STATUS_SUCCESS" in {p.code for p in res.passed}


def test_failed_status_is_not_automatically_classified_as_a_forged_image():
    res = rules_engine.evaluate(receipt(status="Payment failed"), ctx())
    assert "R_STATUS_NOT_SUCCESS" in codes(res)
    assert compose_verdict(res.violations, "standard").verdict == "SUSPICIOUS"


def test_strictness_changes_thresholds():
    res = rules_engine.evaluate(receipt(timestamp="20 Oct 2026, 02:20 PM", status_bar_time="14:21"), ctx())
    # An old screenshot is a merchant-safety warning at every strictness level, but it is not proof that
    # the image itself was forged.
    assert compose_verdict(res.violations, "standard").verdict == "SUSPICIOUS"
    assert compose_verdict(res.violations, "lenient").verdict == "SUSPICIOUS"


def test_sms_match_confirms_and_reuse_blocks_confirmation():
    assert compose_verdict([], "standard", sms_matched=True).verdict == "CONFIRMED"
    from app.schemas.rules import ReasonDetail
    reused = ReasonDetail(code="DUP_UTR_REUSED", severity="CRITICAL", layer="duplicate", title="t", message="m",
                          penalty=50)
    assert compose_verdict([reused], "standard", sms_matched=True).verdict == "LIKELY FAKE"


def test_words_to_number_indian_system():
    assert words_to_number("Rupees Five Hundred Only") == 500
    assert words_to_number("One Thousand Two Hundred Fifty") == 1250
    assert words_to_number("Rupees One Lakh Twenty Five Thousand Only") == 125000
    assert words_to_number("Rupees Ten and Fifty Paise Only") == 10.5
    assert words_to_number("Payment successful") is None


@pytest.mark.parametrize("text,expected", [
    ("23 Oct 2026, 02:32 PM", datetime(2026, 10, 23, 14, 32)),
    ("230ct2026,02:32AM", datetime(2026, 10, 23, 2, 32)),
    ("Oct 23, 2026 2:32 PM", datetime(2026, 10, 23, 14, 32)),
    ("2:32 pm on 23 Oct 2026", datetime(2026, 10, 23, 14, 32)),
    ("23/10/2026 14:32", datetime(2026, 10, 23, 14, 32)),
    ("23-10-26, 12:05 am", datetime(2026, 10, 23, 0, 5)),
    ("23rd Oct 26, 03:08 pm", datetime(2026, 10, 23, 15, 8)),
    ("Date & Time 23rd Oct 26, 03:08 pm", datetime(2026, 10, 23, 15, 8)),
    ("Oct 23, '26 3:08 PM", datetime(2026, 10, 23, 15, 8)),
])
def test_parse_datetime(text, expected):
    assert parse_datetime(text) == expected


def test_dummy_utr_detection():
    assert is_dummy_utr("345678901234")
    assert is_dummy_utr("987654321098")
    assert not is_dummy_utr("429182736451")


def test_receiver_account_name_can_differ_from_store_name():
    ex = receipt(receiver_upi_id=None, receiver="AHASAN ZAFAR")
    res = rules_engine.evaluate(ex, ctx(merchant_receiver_name="Ahasan Zafar"))
    assert "R_RECEIVER_NAME_DIVERGENT" not in codes(res)
    assert "R_RECEIVER_NOT_VISIBLE" in codes(res)
    assert "R_RECEIVER_NAME_MATCH" in {p.code for p in res.passed}


def test_paid_status_is_success_even_when_app_brand_is_not_recognised():
    ex = receipt(status="Paid")
    ex.payment_app = "generic"
    res = rules_engine.evaluate(ex, ctx())
    assert "R_STATUS_NOT_SUCCESS" not in codes(res)
    assert "R_STATUS_SUCCESS" in {p.code for p in res.passed}


def test_unsuccessful_is_not_mistaken_for_successful():
    res = rules_engine.evaluate(receipt(status="Unsuccessful"), ctx())
    assert "R_STATUS_NOT_SUCCESS" in codes(res)
    assert "R_STATUS_SUCCESS" not in {p.code for p in res.passed}
    assert compose_verdict(res.violations, "standard").verdict == "SUSPICIOUS"
