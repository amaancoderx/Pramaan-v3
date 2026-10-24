import pytest

from app.services.sms_parser import mask_sensitive, match, parse_sms


@pytest.mark.parametrize("sms,amount,utr,bank", [
    ("Dear Customer, INR 1,250.00 credited to A/c XX4321 on 23-10-26 by UPI Ref No 429182736451 - HDFC Bank",
     1250.0, "429182736451", "HDFC"),
    ("Your A/C *7890 Credited by Rs 500.00 on 23Oct26. Transfer from rahul@upi UPI Ref No: 998877665544 -SBI",
     500.0, "998877665544", "SBI"),
    ("ICICI Bank Acct XX512 credited with Rs 2,750.00 on 23-Oct-26; RAHUL VERMA credited. UPI:612398745612.",
     2750.0, "612398745612", "ICICI"),
    ("Rs.899 received in your Kotak Bank a/c XX0042 from priya@oksbi. UPI Ref 501234567890",
     899.0, "501234567890", "KOTAK"),
    ("A/c XXXXXX1234 is credited for INR 12,500 on 23/10/26 by UPI/CR/436712093487/AMIT PATEL. -Axis Bank",
     12500.0, "436712093487", "AXIS"),
])
def test_parse_credit_sms(sms, amount, utr, bank):
    r = parse_sms(sms)
    assert r["parsed"] and r["direction"] == "credit"
    assert r["amount"] == amount
    assert r["utr"] == utr
    assert r["bank"] == bank
    assert r["account_masked"] and r["account_masked"].startswith("XX")


def test_debit_sms_cannot_confirm():
    r = parse_sms("Rs 750.00 debited from A/c XX1111 on 23-10-26 to VPA shop@okaxis. UPI Ref 429182736451 - SBI")
    assert r["direction"] == "debit"
    m = match(r, 750.0, "429182736451")
    assert m["status"] == "SMS_MISMATCH"


def test_match_success():
    r = parse_sms("INR 750.00 credited to A/c XX1111 by UPI Ref 429182736451")
    m = match(r, 750.0, "429182736451")
    assert m["status"] == "SMS_MATCHED" and m["amount_matched"] and m["utr_matched"]


def test_same_utr_different_amount_is_critical():
    m = match(parse_sms("INR 75.00 credited to A/c XX1111 by UPI Ref 429182736451"), 750.0, "429182736451")
    assert m["code"] == "GT_SMS_AMOUNT_MISMATCH" and m["severity"] == "CRITICAL"


def test_different_utr_is_mismatch():
    m = match(parse_sms("INR 750.00 credited to A/c XX1111 by UPI Ref 111122223333"), 750.0, "429182736451")
    assert m["status"] == "SMS_MISMATCH" and m["utr_matched"] is False


def test_masking_keeps_utr_but_hides_accounts_and_phones():
    out = mask_sensitive("A/c 50100234567890 credited. Call 9876543210. UPI Ref 429182736451")
    assert "50100234567890" not in out and "7890" in out
    assert "9876543210" not in out
    assert "429182736451" in out
