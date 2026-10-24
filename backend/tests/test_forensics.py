"""Forensic checks on rendered mock receipts, using the renderer's known text boxes instead of OCR."""
import io
import random
from datetime import datetime

import cv2
import numpy as np
from PIL import Image

from app.schemas.rules import BoundingBox
from app.schemas.verification import ExtractedData, ExtractedField
from app.services.forensics import estimate_jpeg_quality, forensic_engine
from app.services.mock_receipts import _overwrite, encode, random_spec, render_receipt

NOW = datetime(2026, 10, 23, 14, 30)


def rendered(seed=3):
    return render_receipt(random_spec(random.Random(seed), NOW, "Test Kirana", "testkirana@okaxis"))


def as_items_and_fields(r):
    items = [{"text": k, "confidence": 0.99,
              "bbox": {"x": b[0], "y": b[1], "width": b[2] - b[0], "height": b[3] - b[1]}} for k, b in r.boxes.items()]
    fields = {}
    for key in ("amount", "utr", "timestamp", "receiver_upi_id"):
        x0, y0, x1, y1 = r.boxes[key]
        fields[key] = ExtractedField(value="x", confidence=0.99, bbox=BoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0))
    return items, ExtractedData(**fields)


def bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)


def test_clean_receipt_has_no_forensic_findings():
    r = rendered()
    items, ex = as_items_and_fields(r)
    data, _ = encode(r.image)
    out = forensic_engine.analyze(data, bgr(r.image), ex, items, None)
    assert out["reasons"] == [], [x.code for x in out["reasons"]]


def test_painted_over_amount_is_caught():
    r = rendered()
    items, ex = as_items_and_fields(r)  # text boxes as OCR would see them (the new text sits where the old was)
    _overwrite(r, "amount", "₹9,999", random.Random(1), patch_delta=16)
    data, _ = encode(r.image)
    codes = {x.code for x in forensic_engine.analyze(data, bgr(r.image), ex, items, None)["reasons"]}
    assert "F_BACKGROUND_MISMATCH" in codes


def test_copy_move_of_a_non_text_patch():
    r = rendered()
    img = r.image
    w = img.width
    tick = img.crop((w // 2 - 90, int(w / 1080 * 320), w // 2 + 90, int(w / 1080 * 500)))
    img.paste(tick, (40, int(img.height * 0.80)))
    gray = cv2.cvtColor(bgr(img), cv2.COLOR_BGR2GRAY)
    items, _ = as_items_and_fields(r)
    n, src, dst = forensic_engine.copy_move(gray, True, [i["bbox"] for i in items])
    assert n >= 16 and dst is not None
    n_clean, _, _ = forensic_engine.copy_move(cv2.cvtColor(bgr(rendered().image), cv2.COLOR_BGR2GRAY), True,
                                              [i["bbox"] for i in items])
    assert n_clean < 16


def test_editor_metadata_and_recompression():
    r = rendered()
    data, _ = encode(r.image, "PNG", software="Adobe Photoshop 25.4")
    codes = {x.code for x in forensic_engine.inspect_file(data)["reasons"]}
    assert "F_EDITOR_SOFTWARE" in codes

    data, _ = encode(r.image, "JPEG", quality=22)
    info = forensic_engine.inspect_file(data)
    assert 15 <= info["jpeg_quality"] <= 30
    assert "F_HEAVY_RECOMPRESSION" in {x.code for x in info["reasons"]}

    buf = io.BytesIO()
    r.image.save(buf, "JPEG", quality=92)
    assert estimate_jpeg_quality(Image.open(io.BytesIO(buf.getvalue()))) >= 88
