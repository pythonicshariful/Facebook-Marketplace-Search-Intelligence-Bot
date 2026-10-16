"""Browser automation service (Selenium + Chrome).

Responsibilities
* Launch Chrome with an account's dedicated persistent ``--user-data-dir``.
* Track open sessions (one per account), reuse or close them safely.
* Navigate to Marketplace URLs, wait explicitly, classify the page state and
  return the HTML for extraction.

This module never types credentials, never reads cookie *values*, and never
retries a blocked page.  It is only called from background worker threads –
never directly from Flask request handlers.
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
from typing import Callable, Iterator, Optional, Tuple

from . import selectors as S
from .page_state import PageState, classify
from .profile_lock import ProfileBusyError, ProfileLock, chrome_profile_in_use
from ..models import utcnow

log = logging.getLogger("fmbot.browser")

FACEBOOK_HOME = "https://www.facebook.com/"
MARKETPLACE_HOME = "https://www.facebook.com/marketplace/"


@dataclass
class BrowserOptions:
    headless: bool = False
    page_load_timeout: int = 45
    element_wait_timeout: int = 20
    max_scroll_rounds: int = 2
    scroll_pause_seconds: float = 2.5


@dataclass
class FetchResult:
    state: PageState
    detail: str
    url: str = ""
    final_url: str = ""
    html: str = ""


def detect_chrome_version(chrome_binary: str = "") -> Tuple[Optional[str], Optional[int]]:
    """Detect the installed Google Chrome version and its major version integer.

    Before launching undetected-chromedriver, discovering the installed Chrome major
    version prevents ChromeDriver version mismatch errors (SessionNotCreatedException).

    Strategies:
    1. If chrome_binary is provided, check its file/CLI version.
    2. On Windows: query Registry (HKCU/HKLM BLBeacon or Uninstall DisplayVersion).
    3. On Windows: inspect standard installation paths (Program Files, LocalAppData).
    4. Ask undetected_chromedriver.find_chrome_executable() for detected binary.
    5. On Linux/macOS: query standard binary names with --version.
    """
    full_ver: Optional[str] = None
    major_ver: Optional[int] = None

    def _parse_major(v_str: Optional[str]) -> Optional[int]:
        if not v_str:
            return None
        m = re.search(r"(\d+)(?:\.\d+)+", str(v_str))
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        return None

    def _get_win_file_version(filepath: str) -> Optional[str]:
        if not filepath or not os.path.exists(filepath):
            return None
        try:
            import ctypes
            from ctypes import wintypes
            size = ctypes.windll.version.GetFileVersionInfoSizeW(filepath, None)
            if not size:
                return None
            res = ctypes.create_string_buffer(size)
            if not ctypes.windll.version.GetFileVersionInfoW(filepath, None, size, res):
                return None
            uLen = wintypes.UINT()
            pFixed = wintypes.LPVOID()
            if ctypes.windll.version.VerQueryValueW(res, "\\", ctypes.byref(pFixed), ctypes.byref(uLen)):
                class VS_FIXEDFILEINFO(ctypes.Structure):
                    _fields_ = [
                        ("dwSignature", wintypes.DWORD),
                        ("dwStrucVersion", wintypes.DWORD),
                        ("dwFileVersionMS", wintypes.DWORD),
                        ("dwFileVersionLS", wintypes.DWORD),
                        ("dwProductVersionMS", wintypes.DWORD),
                        ("dwProductVersionLS", wintypes.DWORD),
                        ("dwFileFlagsMask", wintypes.DWORD),
                        ("dwFileFlags", wintypes.DWORD),
                        ("dwFileOS", wintypes.DWORD),
                        ("dwFileType", wintypes.DWORD),
                        ("dwFileSubtype", wintypes.DWORD),
                        ("dwFileDateMS", wintypes.DWORD),
                        ("dwFileDateLS", wintypes.DWORD),
                    ]
                fixed = VS_FIXEDFILEINFO.from_address(pFixed.value)
                ms = fixed.dwProductVersionMS
                ls = fixed.dwProductVersionLS
                return f"{ms >> 16}.{ms & 0xffff}.{ls >> 16}.{ls & 0xffff}"
        except Exception:
            pass
        return None

    def _get_cli_version(binary: str) -> Optional[str]:
        if not binary:
            return None
        try:
            out = subprocess.check_output([binary, "--version"], stderr=subprocess.STDOUT, timeout=3, text=True)
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None

    # 1. Custom binary passed explicitly
    if chrome_binary and os.path.exists(chrome_binary):
        if sys.platform.startswith("win"):
            full_ver = _get_win_file_version(chrome_binary)
        else:
            full_ver = _get_cli_version(chrome_binary)
        major_ver = _parse_major(full_ver)
        if major_ver:
            return full_ver, major_ver

    # 2. Windows Registry
    if sys.platform.startswith("win"):
        try:
            import winreg
            candidates = [
                (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon", "version"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon", "version"),
                (winreg.HKEY_CURRENT_USER, r"Software\Chromium\BLBeacon", "version"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Chromium\BLBeacon", "version"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome", "DisplayVersion"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome", "DisplayVersion"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome", "DisplayVersion"),
            ]
            for root, subkey, val_name in candidates:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        v, _ = winreg.QueryValueEx(key, val_name)
                        if v:
                            full_ver = str(v).strip()
                            major_ver = _parse_major(full_ver)
                            if major_ver:
                                return full_ver, major_ver
                except OSError:
                    continue
        except Exception:
            pass

    # 3. Standard Windows Installation Paths
    if sys.platform.startswith("win"):
        common_paths = [
            os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.environ.get("LocalAppData", ""), r"Google\Chrome\Application\chrome.exe"),
        ]
        for cp in common_paths:
            if os.path.exists(cp):
                full_ver = _get_win_file_version(cp)
                major_ver = _parse_major(full_ver)
                if major_ver:
                    return full_ver, major_ver

    # 4. undetected_chromedriver executable discovery fallback
    try:
        import undetected_chromedriver as uc
        exe = uc.find_chrome_executable()
        if exe and os.path.exists(exe):
            if sys.platform.startswith("win"):
                full_ver = _get_win_file_version(exe)
            else:
                full_ver = _get_cli_version(exe)
            major_ver = _parse_major(full_ver)
            if major_ver:
                return full_ver, major_ver
    except Exception:
        pass

    # 5. Non-Windows standard CLI lookups
    if not sys.platform.startswith("win"):
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            p = shutil.which(name)
            if p:
                full_ver = _get_cli_version(p)
                major_ver = _parse_major(full_ver)
                if major_ver:
                    return full_ver, major_ver

    return full_ver, major_ver


def create_chrome_driver(profile_dir: str, headless: bool, page_load_timeout: int,
                         chrome_binary: str = "", chromedriver_path: str = "",
                         version_main: Optional[int] = None):
    """Create an Undetected ChromeDriver bound to a persistent profile.

    Auto-detects the installed Chrome major version beforehand to ensure ChromeDriver
    matches the installed browser and skips version mismatch errors.
    """
    import undetected_chromedriver as uc

    # Detect Chrome version prior to launch to skip version mismatch errors
    detected_full, detected_major = detect_chrome_version(chrome_binary)
    target_major = version_main or detected_major
    if target_major:
        log.info("Detected Chrome %s (targeting major version %s for undetected-chromedriver)",
                 detected_full or f"v{target_major}", target_major)
    else:
        log.warning("Could not auto-detect Chrome version; undetected-chromedriver will attempt default resolution")

    opts = uc.ChromeOptions()
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--window-size=1366,900")
    opts.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        # Do not let Chrome store passwords in the automation profiles.
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    })

    if chrome_binary:
        opts.binary_location = chrome_binary

    driver_kwargs: dict = {
        "options": opts,
        "user_data_dir": str(Path(profile_dir).resolve()),
        "headless": headless,
        "use_subprocess": True,
    }
    if target_major:
        driver_kwargs["version_main"] = target_major
    if chrome_binary:
        driver_kwargs["browser_executable_path"] = chrome_binary
    if chromedriver_path:
        driver_kwargs["driver_executable_path"] = chromedriver_path

    try:
        driver = uc.Chrome(**driver_kwargs)
    except Exception as exc:
        log.error("Failed to initialize undetected-chromedriver (version_main=%s): %s", target_major, exc)
        raise

    driver.set_page_load_timeout(page_load_timeout)
    return driver


DriverFactory = Callable[[str, bool, int], object]


@dataclass
class BrowserSession:
    account_id: int
    label: str
    profile_dir: str
    driver: object
    lock: ProfileLock
    purpose: str
    headless: bool
    opened_at: datetime = field(default_factory=utcnow)
    last_used_at: datetime = field(default_factory=utcnow)
    activity: str = "idle"
    use_lock: threading.Lock = field(default_factory=threading.Lock)

    def alive(self) -> bool:
        try:
            handles = self.driver.window_handles  # type: ignore[attr-defined]
            return bool(handles)
        except Exception:
            return False

    def current_url(self) -> str:
        try:
            return self.driver.current_url  # type: ignore[attr-defined]
        except Exception:
            return ""

    def quit(self) -> None:
        try:
            self.driver.quit()  # type: ignore[attr-defined]
        except Exception:
            log.debug("driver.quit() raised", exc_info=True)
        finally:
            self.lock.release()


class BrowserManager:
    """Registry of open browser sessions, at most one per account/profile."""

    def __init__(self, locks_dir: str | Path, chrome_binary: str = "", chromedriver_path: str = "",
                 driver_factory: Optional[DriverFactory] = None, version_main: Optional[int] = None):
        self.locks_dir = Path(locks_dir)
        self.chrome_binary = chrome_binary
        self.chromedriver_path = chromedriver_path
        self.version_main = version_main
        self._factory = driver_factory
        self._sessions: dict[int, BrowserSession] = {}
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------
    def _make_driver(self, profile_dir: str, headless: bool, page_load_timeout: int):
        if self._factory:
            return self._factory(profile_dir, headless, page_load_timeout)
        return create_chrome_driver(profile_dir, headless, page_load_timeout,
                                    self.chrome_binary, self.chromedriver_path,
                                    version_main=self.version_main)

    def open(self, account_id: int, label: str, profile_dir: str, purpose: str,
             opts: BrowserOptions, force_visible: bool = False) -> BrowserSession:
        """Return an existing live session or launch Chrome for the profile."""
        with self._lock:
            existing = self.get(account_id)
            if existing:
                desired_headless = False if force_visible else opts.headless
                if existing.headless != desired_headless:
                    log.info("Relaunching browser for %s: mode changed (current headless=%s, desired=%s)",
                             label, existing.headless, desired_headless)
                    self.close(account_id)
                else:
                    existing.purpose = purpose
                    existing.lock.set_owner(f"{label}:{purpose}")
                    return existing
            Path(profile_dir).mkdir(parents=True, exist_ok=True)
            lock = ProfileLock(profile_dir, self.locks_dir, owner=f"{label}:{purpose}")
            lock.acquire()  # raises ProfileBusyError
            try:
                # Allow a short grace period for OS to release file locks after previous Chrome shutdown
                for _ in range(10):
                    if not chrome_profile_in_use(profile_dir):
                        break
                    time.sleep(0.2)
                if chrome_profile_in_use(profile_dir):
                    raise ProfileBusyError(
                        "A Chrome window started outside this application is using this profile. "
                        "Close it and try again.")
                headless = False if force_visible else opts.headless
                driver = self._make_driver(profile_dir, headless, opts.page_load_timeout)
            except Exception:
                lock.release()
                raise
            session = BrowserSession(account_id=account_id, label=label, profile_dir=profile_dir,
                                     driver=driver, lock=lock, purpose=purpose, headless=headless)
            self._sessions[account_id] = session
            log.info("Opened browser for %s (%s, headless=%s)", label, purpose, headless)
            return session

    def get(self, account_id: int) -> Optional[BrowserSession]:
        with self._lock:
            s = self._sessions.get(account_id)
            if s and not s.alive():
                log.info("Browser for %s is no longer running; cleaning up", s.label)
                self._sessions.pop(account_id, None)
                s.quit()
                return None
            return s

    def is_open(self, account_id: int) -> bool:
        return self.get(account_id) is not None

    def is_busy(self, account_id: int) -> bool:
        s = self._sessions.get(account_id)
        return bool(s and s.use_lock.locked())

    def close(self, account_id: int) -> bool:
        with self._lock:
            s = self._sessions.pop(account_id, None)
        if not s:
            return False
        s.quit()
        log.info("Closed browser for %s", s.label)
        return True

    def shutdown_all(self) -> None:
        with self._lock:
            ids = list(self._sessions)
        for aid in ids:
            self.close(aid)

    def snapshot(self) -> list[dict]:
        with self._lock:
            items = list(self._sessions.values())
        out = []
        for s in items:
            out.append({"account_id": s.account_id, "label": s.label, "purpose": s.purpose,
                        "activity": s.activity, "busy": s.use_lock.locked(), "headless": s.headless,
                        "opened_at": s.opened_at.isoformat(), "last_used_at": s.last_used_at.isoformat()})
        return out


# --------------------------------------------------------------------------
# Navigation helpers
# --------------------------------------------------------------------------
def _has_login_cookie(driver) -> Optional[bool]:
    try:
        return driver.get_cookie(S.LOGGED_IN_COOKIE) is not None
    except Exception:
        return None


def _body_text(driver) -> Optional[str]:
    try:
        from selenium.webdriver.common.by import By
        return driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return None


def navigate_and_classify(driver, url: str, opts: BrowserOptions, scroll: bool = False) -> FetchResult:
    """Load ``url``, wait for a recognisable state, optionally scroll a little."""
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        driver.get(url)
    except TimeoutException:
        return FetchResult(PageState.TIMEOUT, f"Page load exceeded {opts.page_load_timeout}s", url=url)
    except WebDriverException as exc:
        msg = (exc.msg or str(exc)).split("\n")[0]
        state = PageState.NETWORK_ERROR if "net::ERR" in msg else PageState.BROWSER_ERROR
        return FetchResult(state, msg[:300], url=url)

    def _ready(d):
        cur = (d.current_url or "").lower()
        if any(p in cur for p in S.CHECKPOINT_URL_PATTERNS + S.LOGIN_URL_PATTERNS):
            return True
        for css in [S.LISTING_LINK_CSS] + S.LOGIN_FORM_CSS[:1]:
            if d.find_elements(By.CSS_SELECTOR, css):
                return True
        return False

    try:
        WebDriverWait(driver, opts.element_wait_timeout, poll_frequency=0.5).until(_ready)
    except TimeoutException:
        pass  # classify whatever rendered (may be empty results)
    except WebDriverException as exc:
        return FetchResult(PageState.BROWSER_ERROR, (exc.msg or str(exc))[:300], url=url)

    try:
        state, detail = classify(driver.current_url, driver.page_source, _body_text(driver),
                                 _has_login_cookie(driver))
        if scroll and state == PageState.OK:
            for _ in range(opts.max_scroll_rounds):
                driver.execute_script("window.scrollBy(0, Math.max(800, window.innerHeight * 0.9));")
                time.sleep(opts.scroll_pause_seconds)
        return FetchResult(state, detail, url=url, final_url=driver.current_url, html=driver.page_source)
    except WebDriverException as exc:
        return FetchResult(PageState.BROWSER_ERROR, (exc.msg or str(exc))[:300], url=url)


class Navigator:
    """Navigation API handed to the job runner for one account session."""

    def __init__(self, session: BrowserSession, opts: BrowserOptions):
        self.session = session
        self.opts = opts

    def search(self, url: str) -> FetchResult:
        self.session.activity = "searching"
        self.session.last_used_at = utcnow()
        return navigate_and_classify(self.session.driver, url, self.opts, scroll=True)

    def detail(self, url: str) -> FetchResult:
        self.session.activity = "reading listing"
        self.session.last_used_at = utcnow()
        return navigate_and_classify(self.session.driver, url, self.opts, scroll=False)


class SeleniumFetcher:
    """Provides exclusive Navigator access to an account's browser."""

    def __init__(self, manager: BrowserManager):
        self.manager = manager

    @contextmanager
    def session_for(self, account_id: int, label: str, profile_dir: str, opts: BrowserOptions,
                    keep_open: bool) -> Iterator[Navigator]:
        opened_here = not self.manager.is_open(account_id)
        session = self.manager.open(account_id, label, profile_dir, "monitoring", opts)
        if not session.use_lock.acquire(blocking=False):
            raise ProfileBusyError(f"Browser for {label} is busy with another task")
        try:
            yield Navigator(session, opts)
        finally:
            session.activity = "idle"
            session.use_lock.release()
            if opened_here and not keep_open:
                self.manager.close(account_id)
