"""Browser-profile locking.

Two layers guarantee that only one Chrome process ever uses a given
``--user-data-dir``:

1. An in-process registry (threading) so two worker threads cannot race.
2. A cross-process file lock (``filelock``) in ``data/locks`` so a second
   copy of the backend (or a script) cannot open the same profile.

Additionally ``chrome_profile_in_use`` detects a Chrome instance that was
started *outside* this application against the same directory (Chrome keeps
an exclusive handle on ``<profile>/lockfile`` on Windows).
"""
from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path

from filelock import FileLock, Timeout

from ..models import utcnow


class ProfileBusyError(RuntimeError):
    pass


_registry_lock = threading.Lock()
_holders: dict[str, dict] = {}  # normalized profile path -> {"owner":..., "since":...}


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def holder_info(profile_dir: str | Path) -> dict | None:
    with _registry_lock:
        info = _holders.get(_norm(profile_dir))
        return dict(info) if info else None


def is_locked(profile_dir: str | Path) -> bool:
    return holder_info(profile_dir) is not None


def chrome_profile_in_use(profile_dir: str | Path) -> bool:
    """True if a Chrome process (possibly not ours) holds the profile."""
    p = Path(profile_dir)
    lockfile = p / "lockfile"           # Windows
    if lockfile.exists():
        try:
            with open(lockfile, "a"):
                pass
        except PermissionError:
            return True
    singleton = p / "SingletonLock"     # Linux/macOS (symlink)
    return singleton.is_symlink() or singleton.exists()


class ProfileLock:
    def __init__(self, profile_dir: str | Path, locks_dir: str | Path, owner: str):
        self.profile_dir = _norm(profile_dir)
        self.owner = owner
        name = Path(self.profile_dir).name or "profile"
        Path(locks_dir).mkdir(parents=True, exist_ok=True)
        self._file_lock = FileLock(str(Path(locks_dir) / f"{name}.lock"))
        self.acquired = False

    def acquire(self) -> None:
        with _registry_lock:
            current = _holders.get(self.profile_dir)
            if current is not None:
                raise ProfileBusyError(
                    f"Profile is in use by '{current['owner']}' since {current['since']:%H:%M:%S} UTC")
            try:
                self._file_lock.acquire(timeout=0)
            except Timeout:
                raise ProfileBusyError("Profile is locked by another process of this application")
            _holders[self.profile_dir] = {"owner": self.owner, "since": utcnow()}
            self.acquired = True

    def set_owner(self, owner: str) -> None:
        with _registry_lock:
            if self.profile_dir in _holders:
                _holders[self.profile_dir]["owner"] = owner
                self.owner = owner

    def release(self) -> None:
        with _registry_lock:
            if not self.acquired:
                return
            _holders.pop(self.profile_dir, None)
            try:
                self._file_lock.release(force=True)
            finally:
                self.acquired = False

    def __enter__(self) -> "ProfileLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def snapshot() -> dict[str, dict]:
    with _registry_lock:
        return {k: dict(v) for k, v in _holders.items()}


def _since(dt: datetime) -> str:  # pragma: no cover - formatting helper
    return dt.strftime("%Y-%m-%d %H:%M:%S")
