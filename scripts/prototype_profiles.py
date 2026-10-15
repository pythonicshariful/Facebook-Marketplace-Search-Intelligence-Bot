"""Stage-2 prototype: verify persistent, isolated Chrome profiles + locking.

Usage:  .venv\\Scripts\\python scripts\\prototype_profiles.py [--headless]

* Launches two throw-away profiles under data/prototype_profiles/.
* Writes a different localStorage marker on https://example.com in each.
* Closes and relaunches both, verifying each marker persisted and that the
  profiles did not overwrite each other.
* Verifies the profile lock rejects a second launch on the same profile.
No Facebook access is performed.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config  # noqa: E402
from app.services.browser_service import BrowserManager, BrowserOptions  # noqa: E402
from app.services.profile_lock import ProfileBusyError  # noqa: E402

URL = "https://example.com/"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()
    cfg = Config()
    cfg.ensure_dirs()
    root = cfg.DATA_DIR / "prototype_profiles"
    shutil.rmtree(root, ignore_errors=True)
    profiles = {1: root / "proto_a", 2: root / "proto_b"}
    opts = BrowserOptions(headless=args.headless, page_load_timeout=40)
    mgr = BrowserManager(cfg.LOCKS_DIR, cfg.CHROME_BINARY, cfg.CHROMEDRIVER_PATH)

    try:
        # Round 1: write markers
        for aid, path in profiles.items():
            s = mgr.open(aid, f"proto{aid}", str(path), "prototype", opts)
            caps = s.driver.capabilities
            print(f"[profile {aid}] Chrome {caps.get('browserVersion')} / "
                  f"driver {caps.get('chrome', {}).get('chromedriverVersion', '?').split(' ')[0]}")
            s.driver.get(URL)
            s.driver.execute_script("localStorage.setItem('fmbot_marker', arguments[0]);", f"profile-{aid}")

        # Lock conflict check (same profile while open)
        try:
            from app.services.profile_lock import ProfileLock
            ProfileLock(profiles[1], cfg.LOCKS_DIR, "intruder").acquire()
            print("FAIL: second lock on profile 1 was granted")
            return 1
        except ProfileBusyError as exc:
            print(f"OK: concurrent use of profile 1 rejected -> {exc}")

        mgr.shutdown_all()

        # Round 2: relaunch and verify persistence + isolation
        ok = True
        for aid, path in profiles.items():
            s = mgr.open(aid, f"proto{aid}", str(path), "prototype", opts)
            s.driver.get(URL)
            val = s.driver.execute_script("return localStorage.getItem('fmbot_marker');")
            expected = f"profile-{aid}"
            status = "OK" if val == expected else "FAIL"
            ok &= val == expected
            print(f"{status}: profile {aid} marker after restart = {val!r} (expected {expected!r})")
        mgr.shutdown_all()
        print("PROTOTYPE RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        mgr.shutdown_all()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
