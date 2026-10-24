import os
import random
import sys
import tempfile
from pathlib import Path

# Isolated storage + database per test session; must be set before the app is imported.
_TMP = tempfile.mkdtemp(prefix="pramaan-test-")
os.environ["STORAGE_DIR"] = _TMP
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services.mock_receipts import encode, random_spec, render_receipt  # noqa: E402
from app.services.pipeline import local_now  # noqa: E402

MERCHANT = {"email": "test.shop@example.com", "password": "correct-horse-9", "name": "Test Kirana",
            "registered_upi_id": "testkirana@okaxis"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def auth(client):
    r = client.post("/api/auth/register", json=MERCHANT)
    assert r.status_code == 201, r.text
    body = r.json()
    return {"headers": {"Authorization": f"Bearer {body['access_token']}"}, "merchant": body["merchant"]}


def make_receipt(seed: int = 1, **overrides) -> bytes:
    spec = random_spec(random.Random(seed), local_now(), MERCHANT["name"], MERCHANT["registered_upi_id"])
    for k, v in overrides.items():
        setattr(spec, k, v)
    data, _ = encode(render_receipt(spec).image)
    return data
