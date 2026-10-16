"""Logging configuration with rotating files and secret redaction."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .security import RedactingFilter

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"
_configured = False


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter(LOG_FORMAT)
    redactor = RedactingFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "fmbot.log", maxBytes=5 * 1024 * 1024, backupCount=10, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redactor)

    err_handler = logging.handlers.RotatingFileHandler(
        log_dir / "errors.log", maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(fmt)
    err_handler.addFilter(redactor)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(redactor)

    for h in (file_handler, err_handler, console):
        root.addHandler(h)

    # Quiet noisy libraries
    for noisy in ("urllib3", "selenium.webdriver.remote", "selenium.webdriver.common",
                  "undetected_chromedriver", "apscheduler.executors.default", "waitress.queue"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True
