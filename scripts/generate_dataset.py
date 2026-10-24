"""Generate the synthetic benchmark set: 20 clean + 20 tampered MOCK receipts (generic, brand-free).

    python scripts/generate_dataset.py [--seed 2026] [--out backend/storage/dataset]

Tamper operations are scripted and seeded, so the same seed always produces the same images.
"""
import argparse
import json
import shutil
from pathlib import Path

import _bootstrap  # noqa: F401

from app.config import settings
from app.services.mock_receipts import TAMPER_PLAN, build_dataset
from app.services.pipeline import local_now


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=Path, default=settings.DATASET_DIR)
    args = ap.parse_args()

    now = local_now().replace(second=0, microsecond=0)
    out: Path = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    samples = build_dataset(now, settings.DEMO_MERCHANT_NAME, settings.DEMO_MERCHANT_UPI_ID, seed=args.seed)
    manifest = []
    for s in samples:
        name = f"{s.sample_id.lower()}{s.ext}"
        (out / name).write_bytes(s.image_bytes)
        manifest.append({"id": s.sample_id, "filename": name, "label": s.label, "tamper_type": s.tamper_type,
                         "description": s.description, "amount": s.spec.amount, "utr": s.spec.utr})
        print(f"  {s.sample_id:10} {s.tamper_type:18} {name}")

    meta = {
        "dataset_name": "Pramaan synthetic UPI receipts v1",
        "description": "Generic, brand-free MOCK receipts: 20 clean and 20 with scripted tamper operations ("
                       + ", ".join(f"{k} x{n}" for k, n in TAMPER_PLAN) + ").",
        "seed": args.seed,
        "generated_at": now.isoformat(),
        "reference_time": now.isoformat(),
        "timezone": settings.TIMEZONE,
        "merchant": {"name": settings.DEMO_MERCHANT_NAME, "upi_id": settings.DEMO_MERCHANT_UPI_ID,
                     "allowed_window_minutes": 60, "strictness": "standard"},
        "samples": manifest,
    }
    (out / "manifest.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nWrote {len(samples)} images and manifest.json to {out}")


if __name__ == "__main__":
    main()
