"""End-to-end: register -> upload -> verdict -> corrections -> bank SMS -> report, plus bad inputs."""
import io

import numpy as np
from PIL import Image, ImageFilter

from tests.conftest import MERCHANT, make_receipt


def upload(client, headers, data: bytes, name="receipt.png", mime="image/png", **form):
    return client.post("/api/verify/analyze", headers=headers, files={"file": (name, data, mime)}, data=form)


def test_health_and_public_endpoints(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert "apps" in client.get("/api/rules").json()
    assert client.get("/api/benchmark/results").status_code == 200


def test_auth_required(client):
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 401 and r.json()["detail"]["code"] == "UNAUTHORIZED"
    assert client.get("/api/dashboard/stats", headers={"X-API-Key": "nope"}).status_code == 401


def test_login_and_wrong_password(client, auth):
    ok = client.post("/api/auth/login", json={"email": MERCHANT["email"], "password": MERCHANT["password"]})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/api/auth/login", json={"email": MERCHANT["email"], "password": "shopkeeper123"})
    assert bad.status_code == 401


def test_full_flow(client, auth):
    h = auth["headers"]
    r = upload(client, h, make_receipt(seed=11))
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["verdict"] == "LIKELY GENUINE", [x["code"] for x in v["reasons"]]
    ex = v["extracted_data"]
    assert ex["receiver_upi_id"]["value"] == MERCHANT["registered_upi_id"]
    assert len(ex["utr"]["value"]) == 12 and ex["amount"]["value"]
    assert ex["amount"]["bbox"] and v["image_available"] and v["heatmap_url"]
    assert client.get(v["image_url"]).status_code == 200
    assert v["processing_time_seconds"] < 30

    # Correct a field: a wrong amount is now inconsistent with the amount in words.
    c = client.post(f"/api/verify/{v['id']}/corrections", headers=h, json={"amount": "99999"}).json()
    assert c["extracted_data"]["amount"]["corrected"] is True
    assert any(x["code"] == "R_AMT_WORDS_MISMATCH" for x in c["reasons"])
    c = client.post(f"/api/verify/{v['id']}/corrections", headers=h, json={"amount": ex["amount"]["value"]}).json()
    assert c["verdict"] == "LIKELY GENUINE"

    # Bank SMS with the same UTR and amount confirms the payment.
    sms = f"INR {float(ex['amount']['value']):,.2f} credited to A/c XX4321 by UPI Ref No {ex['utr']['value']} - HDFC"
    s = client.post(f"/api/verify/{v['id']}/sms", headers=h, json={"sms_text": sms}).json()
    assert s["verdict"] == "CONFIRMED" and s["ground_truth"]["status"] == "SMS_MATCHED"
    assert s["ground_truth"]["account_masked"] == "XX4321"

    hd = client.post(f"/api/verify/{v['id']}/handled", headers=h, json={"handled": True}).json()
    assert hd["handled"] is True

    pdf = client.get(f"/api/verify/{v['id']}/report", headers=h)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

    pub = client.get(f"/api/public/verify/{v['id']}").json()
    assert pub["verdict"] == "CONFIRMED" and ex["utr"]["value"] not in pub["utr_masked"]

    # The same screenshot again, cropped and re-compressed, is caught as reused.
    img = Image.open(io.BytesIO(make_receipt(seed=11))).convert("RGB")
    buf = io.BytesIO()
    img.crop((0, 90, img.width, int(img.height * 0.9))).save(buf, "JPEG", quality=70)
    again = upload(client, h, buf.getvalue(), "again.jpg", "image/jpeg").json()
    assert again["is_reused"] and again["verdict"] == "LIKELY FAKE"
    assert again["reused_first_seen"]["id"] == v["id"]

    stats = client.get("/api/dashboard/stats", headers=h).json()
    assert stats["total_checks"] >= 2 and stats["reused_count"] >= 1
    hist = client.get("/api/dashboard/history", headers=h, params={"search": ex["utr"]["value"]}).json()
    assert hist["total"] >= 2


def test_receiver_mismatch_is_fake(client, auth):
    r = upload(client, auth["headers"], make_receipt(seed=12, receiver_upi="someoneelse@ybl")).json()
    assert r["verdict"] == "SUSPICIOUS"
    assert r["reasons"][0]["severity"] == "CRITICAL"
    assert any(x["code"] == "R_RECEIVER_MISMATCH" for x in r["reasons"])


def test_api_key_and_order_bound_qr(client, auth):
    key = {"X-API-Key": auth["merchant"]["api_key"]}
    order = client.post("/api/qr/generate", headers=key, json={"amount": 640}).json()
    assert order["upi_uri"].startswith("upi://pay?pa=") and f"tn={order['order_ref']}" in order["upi_uri"]
    # A receipt for a different amount without the order reference is flagged.
    r = upload(client, key, make_receipt(seed=13, amount=999.0), order_ref=order["order_ref"]).json()
    assert any(x["code"] == "R_ORDER_REF_MISSING" and x["severity"] == "CRITICAL" for x in r["reasons"])
    # The matching receipt carries the reference in its note.
    r = upload(client, key, make_receipt(seed=14, amount=640.0, note=order["order_ref"]),
               order_ref=order["order_ref"]).json()
    assert r["order"]["matched_by"] == "reference"
    assert client.get("/api/qr/orders", headers=key, params={"status": "paid"}).json()["items"]


def test_bad_inputs(client, auth):
    h = auth["headers"]
    r = upload(client, h, b"plain text, not an image", "a.txt", "text/plain")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "NOT_AN_IMAGE"

    big = upload(client, h, b"\x89PNG" + b"0" * (10 * 1024 * 1024 + 10))
    assert big.status_code == 413

    blurry = Image.open(io.BytesIO(make_receipt(seed=15))).filter(ImageFilter.GaussianBlur(9))
    buf = io.BytesIO()
    blurry.save(buf, "PNG")
    r = upload(client, h, buf.getvalue())
    assert r.status_code == 422 and r.json()["detail"]["code"] == "IMAGE_QUALITY_LOW"

    blank = Image.fromarray(np.full((1600, 720, 3), 245, np.uint8))
    noise = Image.effect_noise((720, 1600), 60).convert("RGB")
    buf = io.BytesIO()
    Image.blend(blank, noise, 0.5).save(buf, "PNG")
    r = upload(client, h, buf.getvalue())
    assert r.status_code == 422


def test_other_merchant_cannot_read_check(client, auth):
    v = upload(client, auth["headers"], make_receipt(seed=16)).json()
    other = client.post("/api/auth/register", json={**MERCHANT, "email": "other@example.com"}).json()
    r = client.get(f"/api/verify/{v['id']}", headers={"Authorization": f"Bearer {other['access_token']}"})
    assert r.status_code == 404
