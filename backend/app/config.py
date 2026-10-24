import secrets
import warnings
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

_DEV_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    """All runtime configuration. Every field can be overridden with an env var of the same name
    (or a backend/.env file)."""

    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore", case_sensitive=True)

    PROJECT_NAME: str = "Pramaan"
    PROJECT_VERSION: str = "1.1.0"
    ENV: str = "development"

    SECRET_KEY: str = _DEV_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Comma separated list, e.g. "http://localhost:3000,https://pramaan.example.com"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    # Where the web app is served; used for the public-verify QR printed in PDF reports.
    PUBLIC_APP_URL: str = "http://localhost:3000"

    STORAGE_DIR: Path = BASE_DIR / "storage"
    RULES_PATH: Path = BASE_DIR / "app" / "rules.yaml"
    DATABASE_URL: str = ""

    TIMEZONE: str = "Asia/Kolkata"
    RETENTION_HOURS: int = 24
    PURGE_INTERVAL_MINUTES: int = 30

    MAX_IMAGE_SIZE_MB: int = 10
    MIN_IMAGE_DIMENSION: int = 250
    MIN_FOCUS_SCORE: float = 35.0

    # Demo merchant, created on first start so the app is usable out of the box.
    SEED_DEMO_DATA: bool = True
    SEED_DEMO_COUNT: int = 24
    OCR_THREADS: int = 0  # 0 = onnxruntime default; 1 suits tiny shared CPUs
    DEMO_MERCHANT_EMAIL: str = "merchant@pramaan.local"
    DEMO_MERCHANT_PASSWORD: str = "shopkeeper123"
    DEMO_MERCHANT_NAME: str = "Sharma Kirana Store"
    DEMO_MERCHANT_UPI_ID: str = "sharmakirana@okhdfcbank"
    DEMO_MERCHANT_API_KEY: str = "prm_demo_7f3a9c2e41b84d6f"

    @field_validator("STORAGE_DIR", "RULES_PATH", mode="before")
    @classmethod
    def _as_path(cls, v):
        return Path(v)

    @field_validator("PUBLIC_APP_URL", mode="before")
    @classmethod
    def _with_scheme(cls, v):
        v = str(v).strip().rstrip("/")
        return v if v.startswith("http") else f"https://{v}"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def UPLOAD_DIR(self) -> Path:
        return self.STORAGE_DIR / "uploads"

    @property
    def REPORTS_DIR(self) -> Path:
        return self.STORAGE_DIR / "reports"

    @property
    def DATASET_DIR(self) -> Path:
        return self.STORAGE_DIR / "dataset"

    @property
    def BENCHMARK_PATH(self) -> Path:
        return self.STORAGE_DIR / "benchmark_results.json"

    @property
    def database_url(self) -> str:
        return self.DATABASE_URL or f"sqlite:///{(self.STORAGE_DIR / 'pramaan.db').as_posix()}"


settings = Settings()

if settings.SECRET_KEY == _DEV_SECRET:
    if settings.ENV == "production":
        raise RuntimeError("SECRET_KEY must be set in production.")
    # A random per-process key would log everyone out on restart, so dev keeps a fixed key but warns.
    warnings.warn("SECRET_KEY not set; using an insecure development key.", stacklevel=1)

for _d in (settings.STORAGE_DIR, settings.UPLOAD_DIR, settings.REPORTS_DIR, settings.DATASET_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def new_api_key() -> str:
    return f"prm_{secrets.token_hex(16)}"
