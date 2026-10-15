"""Database initialization and schema validation script."""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config
from app.db import create_all, get_engine, init_engine
from app.security import init_secret_box


def main():
    print("Initialising database...")
    cfg = Config()
    cfg.ensure_dirs()
    if cfg.FERNET_KEY:
        init_secret_box(cfg.FERNET_KEY)

    engine = init_engine(cfg.DATABASE_URL, echo=True)
    create_all()

    with engine.connect() as conn:
        print("Connected successfully. Verifying SQLite Pragmas:")
        for pragma in ["journal_mode", "foreign_keys", "synchronous"]:
            val = conn.exec_driver_sql(f"PRAGMA {pragma};").scalar()
            print(f"  PRAGMA {pragma} = {val}")

    print("\nDatabase initialisation complete at:", cfg.DATABASE_URL)


if __name__ == "__main__":
    main()
