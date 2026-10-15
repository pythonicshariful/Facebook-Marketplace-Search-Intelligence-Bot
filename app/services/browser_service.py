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
from typing import Callable, Iterator, Optional

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


def create_chrome_driver(profile_dir: str, headless: bool, page_load_timeout: int,
                         chrome_binary: str = "", chromedriver_path: str = ""):
    """Create a standard Selenium Chrome driver bound to a persistent profile.

    Selenium Manager (bundled with Selenium >= 4.6) resolves a ChromeDriver that
    matches the installed Chrome when ``chromedriver_path`` is empty.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opts = Options()
    opts.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")
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
    if headless:
        opts.add_argument("--headless=new")
    if chrome_binary:
        opts.binary_location = chrome_binary
    service = Service(executable_path=chromedriver_path) if chromedriver_path else Service()
    driver = webdriver.Chrome(options=opts, service=service)
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
            _ = self.driver.window_handles  # type: ignore[attr-defined]
            return True
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
                 driver_factory: Optional[DriverFactory] = None):
        self.locks_dir = Path(locks_dir)
        self.chrome_binary = chrome_binary
        self.chromedriver_path = chromedriver_path
        self._factory = driver_factory
        self._sessions: dict[int, BrowserSession] = {}
        self._lock = threading.RLock()

    # -- lifecycle ---------------------------------------------------------
    def _make_driver(self, profile_dir: str, headless: bool, page_load_timeout: int):
        if self._factory:
            return self._factory(profile_dir, headless, page_load_timeout)
        return create_chrome_driver(profile_dir, headless, page_load_timeout,
                                    self.chrome_binary, self.chromedriver_path)

    def open(self, account_id: int, label: str, profile_dir: str, purpose: str,
             opts: BrowserOptions, force_visible: bool = False) -> BrowserSession:
        """Return an existing live session or launch Chrome for the profile."""
        with self._lock:
            existing = self.get(account_id)
            if existing:
                existing.purpose = purpose
                existing.lock.set_owner(f"{label}:{purpose}")
                return existing
            Path(profile_dir).mkdir(parents=True, exist_ok=True)
            lock = ProfileLock(profile_dir, self.locks_dir, owner=f"{label}:{purpose}")
            lock.acquire()  # raises ProfileBusyError
            try:
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
