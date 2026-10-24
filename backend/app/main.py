import asyncio
import os
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import auth, dashboard, orders, system, verification
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import DuplicateHash, Merchant, Order, Verification  # noqa: F401  (register tables)
from app.services.ocr_engine import ocr_engine
from app.services.retention import purge_expired
from app.services.seed import ensure_demo_merchant, seed_history

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pramaan")


def _seed_in_background() -> None:
    # Let startup and the first health checks finish before the memory-heavy OCR runs.
    time.sleep(30)
    with SessionLocal() as db:
        try:
            seed_history(db, ensure_demo_merchant(db), count=settings.SEED_DEMO_COUNT)
        except Exception:  # pragma: no cover - demo data must never take the API down
            log.exception("demo seeding failed")


async def _purge_loop() -> None:
    while True:
        await asyncio.sleep(settings.PURGE_INTERVAL_MINUTES * 60)
        with SessionLocal() as db:
            await asyncio.to_thread(purge_expired, db)


def _ensure_schema_compatibility() -> None:
    """Add new nullable merchant fields to existing local databases without deleting demo data."""
    inspector = inspect(engine)
    if "merchants" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("merchants")}
        if "registered_receiver_name" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE merchants ADD COLUMN registered_receiver_name VARCHAR(100)"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_schema_compatibility()
    await asyncio.to_thread(ocr_engine.warm_up)
    with SessionLocal() as db:
        purge_expired(db)
        if settings.SEED_DEMO_DATA:
            ensure_demo_merchant(db)
    # Sample history runs OCR on generated receipts, which overflows Render's 512 MB free instance.
    if settings.SEED_DEMO_DATA and settings.SEED_DEMO_COUNT > 0 and not os.environ.get("RENDER"):
        threading.Thread(target=_seed_in_background, name="seed", daemon=True).start()
    task = asyncio.create_task(_purge_loop())
    yield
    task.cancel()


TAGS = [
    {"name": "Verification", "description": "Analyse screenshots, correct fields, confirm with bank SMS, reports."},
    {"name": "Auth", "description": "Merchant accounts. Use the returned JWT as `Authorization: Bearer`."},
    {"name": "Dashboard", "description": "Merchant history and statistics."},
    {"name": "Orders", "description": "Order-bound UPI QR codes."},
    {"name": "Public", "description": "No authentication required."},
    {"name": "Demo", "description": "Mock receipts for trying the pipeline."},
]

app = FastAPI(
    title="Pramaan API",
    version=settings.PROJECT_VERSION,
    description=(
        "Verify UPI payment screenshots before handing over goods.\n\n"
        "Every merchant endpoint accepts **either** `Authorization: Bearer <jwt>` (from `/api/auth/login`) **or** "
        "`X-API-Key: <key>` (Settings page). Click **Authorize** to try requests here.\n\n"
        "Verdicts: `CONFIRMED` (bank SMS matched), `LIKELY GENUINE`, `SUSPICIOUS`, `LIKELY FAKE`. "
        "A screenshot alone never produces `CONFIRMED`."
    ),
    openapi_tags=TAGS,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    msg = str(first.get("msg", "Invalid request")).removeprefix("Value error, ")
    return JSONResponse(status_code=422,
                        content={"detail": {"code": "VALIDATION_ERROR", "message": f"{field}: {msg}"}})


# Screenshots and heatmaps are stored under random 128-bit names and deleted after RETENTION_HOURS.
app.mount("/api/storage/uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="uploads")

app.include_router(system.router, prefix="/api")
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(verification.router, prefix="/api", tags=["Verification"])
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(orders.router, prefix="/api", tags=["Orders"])


@app.get("/", include_in_schema=False)
def root():
    return {"app": "Pramaan API", "version": settings.PROJECT_VERSION, "docs": "/docs", "health": "/api/health"}
