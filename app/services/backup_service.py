"""Database and configuration backup service.

Provides:
- SQLite hot backup using the SQLite backup API (safe while in WAL mode).
- Snapshot of application configuration and account metadata (non-sensitive).
- ZIP packaging with timestamp naming.
- Automatic retention pruning (retains N latest or N days based on settings).
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import account_service
from . import activity
from . import settings_store as st
from ..config import Config
from ..db import session_scope
from ..models import utcnow

log = logging.getLogger("fmbot.backup")


def create_backup(cfg: Config) -> Path:
    """Create a consistent full backup archive in data/backups/."""
    cfg.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = utcnow().strftime("%Y%m%d_%H%M%S")
    archive_path = cfg.BACKUP_DIR / f"fmbot_backup_{timestamp}.zip"
    temp_dir = cfg.BACKUP_DIR / f"tmp_{timestamp}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        from ..db import get_engine
        get_engine()
    except RuntimeError:
        from ..db import init_engine
        init_engine(cfg.DATABASE_URL)
        if cfg.FERNET_KEY:
            from ..security import init_secret_box
            init_secret_box(cfg.FERNET_KEY)

    try:
        # 1. Hot SQLite backup
        db_src = cfg.DATA_DIR / "app.db"
        if db_src.exists():
            db_dest = temp_dir / "app.db"
            src_conn = sqlite3.connect(str(db_src))
            dest_conn = sqlite3.connect(str(db_dest))
            with dest_conn:
                src_conn.backup(dest_conn)
            dest_conn.close()
            src_conn.close()

        # 2. Dump non-sensitive account metadata & settings
        with session_scope() as s:
            acc_meta = account_service.metadata(s)
            app_settings = st.get_all(s)

        manifest = {
            "created_at": utcnow().isoformat(),
            "version": "1.0.0",
            "accounts_count": len(acc_meta),
            "settings": app_settings,
        }
        (temp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (temp_dir / "accounts.json").write_text(json.dumps(acc_meta, indent=2), encoding="utf-8")

        # 3. Create zip archive
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in temp_dir.iterdir():
                zf.write(item, arcname=item.name)

        log.info("Created backup archive: %s (%d bytes)", archive_path.name, archive_path.stat().st_size)
        activity.info("system", f"Database and configuration backup created: {archive_path.name}")

        # 4. Prune old backups based on retention settings
        with session_scope() as s:
            retention_days = st.get(s, "backup_retention")
        prune_backups(cfg, retention_days=retention_days)

        return archive_path
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def prune_backups(cfg: Config, retention_days: int = 14) -> int:
    cutoff = datetime.now() - timedelta(days=max(1, retention_days))
    deleted_count = 0
    for p in cfg.BACKUP_DIR.glob("fmbot_backup_*.zip"):
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if mtime < cutoff:
                p.unlink()
                deleted_count += 1
        except Exception as exc:
            log.warning("Could not delete old backup %s: %s", p, exc)
    if deleted_count > 0:
        log.info("Pruned %d expired backup archives (retention %d days)", deleted_count, retention_days)
    return deleted_count


def list_backups(cfg: Config) -> list[dict]:
    results = []
    if not cfg.BACKUP_DIR.exists():
        return results
    for p in sorted(cfg.BACKUP_DIR.glob("fmbot_backup_*.zip"), reverse=True):
        stat = p.stat()
        results.append({
            "filename": p.name,
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return results
