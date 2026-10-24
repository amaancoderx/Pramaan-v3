"""Privacy retention: screenshots and heatmaps are deleted after RETENTION_HOURS. The check record (verdict,
masked text, fingerprints) is kept so history and reuse detection keep working."""
import logging
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.merchant import utcnow
from app.models.verification import Verification

log = logging.getLogger("pramaan.retention")


def purge_expired(db: Session) -> int:
    cutoff = utcnow() - timedelta(hours=settings.RETENTION_HOURS)
    rows = (db.query(Verification)
            .filter(Verification.created_at < cutoff, Verification.image_purged_at.is_(None)).all())
    for v in rows:
        for name in (v.image_filename, v.heatmap_filename):
            if name:
                (settings.UPLOAD_DIR / name).unlink(missing_ok=True)
        v.image_filename = v.heatmap_filename = None
        v.image_purged_at = utcnow()
    db.commit()

    # Stray files (crashed uploads, files from an older database) are removed by age as well.
    limit = time.time() - settings.RETENTION_HOURS * 3600
    stray = 0
    for d in (settings.UPLOAD_DIR, settings.REPORTS_DIR):
        for p in d.iterdir():
            if p.is_file() and p.stat().st_mtime < limit:
                p.unlink(missing_ok=True)
                stray += 1
    if rows or stray:
        log.info("retention: purged %d check images, %d stray files", len(rows), stray)
    return len(rows) + stray
