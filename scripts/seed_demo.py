"""Create the demo merchant and a realistic history by running mock receipts through the real pipeline.

    python scripts/seed_demo.py [--reset] [--count 24]

The API does this automatically on first start when SEED_DEMO_DATA=true; use this to rebuild it on demand.
--reset deletes the local SQLite database and stored screenshots first.
"""
import argparse
import shutil

import _bootstrap  # noqa: F401

from app.config import settings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset", action="store_true", help="delete the local database and uploads first")
    ap.add_argument("--count", type=int, default=24)
    args = ap.parse_args()

    if args.reset:
        db_file = settings.STORAGE_DIR / "pramaan.db"
        for suffix in ("", "-wal", "-shm"):
            p = db_file.with_name(db_file.name + suffix)
            p.unlink(missing_ok=True)
        shutil.rmtree(settings.UPLOAD_DIR, ignore_errors=True)
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        print("Reset local database and uploads.")

    from app.database import Base, SessionLocal, engine
    from app.models import DuplicateHash, Merchant, Order, Verification  # noqa: F401
    from app.services.ocr_engine import ocr_engine
    from app.services.seed import ensure_demo_merchant, seed_history

    Base.metadata.create_all(bind=engine)
    ocr_engine.warm_up()
    with SessionLocal() as db:
        m = ensure_demo_merchant(db)
        n = seed_history(db, m, count=args.count)
    print(f"Demo merchant: {settings.DEMO_MERCHANT_EMAIL} / {settings.DEMO_MERCHANT_PASSWORD}")
    print(f"Seeded {n} checks." if n else "Demo merchant already has history; nothing to do (use --reset).")


if __name__ == "__main__":
    main()
