"""Production entrypoint for Marketplace Vehicle Search Intelligence Bot.

Uses Waitress WSGI server bound to 127.0.0.1:8080 by default to ensure safe,
reliable operation without exposing Flask's development server.
"""
from __future__ import annotations

import logging
import sys

from waitress import serve

from app import create_app
from app.config import Config

log = logging.getLogger("fmbot.run")


def main() -> int:
    cfg = Config()
    app = create_app(cfg, start_scheduler=True)

    print("=" * 70)
    print("  Facebook Marketplace Vehicle Search Intelligence Bot")
    print(f"  Dashboard listening at: http://{cfg.HOST}:{cfg.PORT}")
    print(f"  Chrome profiles directory: {cfg.PROFILES_DIR}")
    print(f"  Database path: {cfg.DATA_DIR / 'app.db'}")
    print("=" * 70)

    try:
        serve(app, host=cfg.HOST, port=cfg.PORT, threads=6)
        return 0
    except KeyboardInterrupt:
        print("\nShutdown requested by operator. Cleaning up...")
        scheduler = app.extensions.get("scheduler")
        if scheduler:
            scheduler.stop()
        return 0
    except Exception as exc:
        log.exception("Fatal server error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
