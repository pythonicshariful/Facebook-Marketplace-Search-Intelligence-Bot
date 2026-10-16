"""Telegram Bot API notifications with bounded retries.

The bot token is never logged: error messages are built from status codes /
exception class names only and additionally passed through ``redact``.
"""
from __future__ import annotations

import html
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import settings_store as st
from ..models import Listing, Notification, NotifyStatus, SearchConfiguration, Account, utcnow
from ..security import redact, register_secret

log = logging.getLogger("fmbot.telegram")
API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(redact(message))
        self.retryable = retryable


class TelegramClient:
    def __init__(self, token: str, chat_id: str, timeout: float = 15, max_retries: int = 3,
                 http: Optional[requests.Session] = None, sleep=time.sleep):
        if not token or not chat_id:
            raise TelegramError("Telegram bot token and chat ID must both be configured")
        register_secret(token)
        self._token = token
        self.chat_id = chat_id
        self.timeout = timeout
        self.max_retries = max(1, max_retries)
        self.http = http or requests.Session()
        self._sleep = sleep

    def _call(self, method: str, payload: dict) -> dict:
        url = API.format(token=self._token, method=method)
        last: TelegramError | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.http.post(url, json=payload, timeout=self.timeout)
            except requests.RequestException as exc:
                last = TelegramError(f"Network error contacting Telegram ({type(exc).__name__})", retryable=True)
            else:
                try:
                    data = resp.json()
                except ValueError:
                    data = {}
                if resp.status_code == 200 and data.get("ok"):
                    return data.get("result") or {}
                desc = str(data.get("description") or resp.reason or "")[:200]
                if resp.status_code == 429:
                    wait = min(int((data.get("parameters") or {}).get("retry_after", 5)), 60)
                    last = TelegramError(f"Telegram rate limit (429), retry after {wait}s", retryable=True)
                    if attempt < self.max_retries:
                        self._sleep(wait)
                        continue
                elif resp.status_code >= 500:
                    last = TelegramError(f"Telegram server error {resp.status_code}: {desc}", retryable=True)
                else:
                    # 400/401/403/404: configuration problem – do not retry
                    raise TelegramError(f"Telegram rejected the request ({resp.status_code}): {desc}")
            if attempt < self.max_retries:
                self._sleep(min(2 ** attempt, 30))
        assert last is not None
        raise last

    def send_message(self, text: str, disable_preview: bool = False, silent: bool = False) -> str:
        result = self._call("sendMessage", {
            "chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview, "disable_notification": silent,
        })
        return str(result.get("message_id", ""))


# --------------------------------------------------------------------------
def _fmt_time(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    local = dt.replace(tzinfo=timezone.utc).astimezone()
    return local.strftime("%Y-%m-%d %H:%M %Z").strip()


def format_listing_message(listing: Listing, search_name: str, account_label: str,
                           kind: str = "new", previous_price_cents: Optional[int] = None) -> str:
    e = html.escape
    header = "🚗 <b>New matching listing</b>" if kind == "new" else "📉 <b>Price drop</b>"
    price = listing.price_text or ("Unknown" if listing.price_cents is None else f"${listing.price_cents/100:,.0f}")
    lines = [header, "", f"<b>{e(listing.title or 'Untitled listing')}</b>",
             f"💲 Price: {e(price)}"]
    if kind == "price_drop" and previous_price_cents is not None:
        lines[-1] += f" (was ${previous_price_cents/100:,.0f})"
    lines.append(f"📍 Location: {e(listing.location or '—')}")
    if listing.condition:
        lines.append(f"🔧 Condition: {e(listing.condition)}")
    if listing.mileage:
        lines.append(f"🛣 Mileage: {e(listing.mileage)}")
    if listing.seller_name:
        lines.append(f"👤 Seller: {e(listing.seller_name)}")
    if listing.posted_text:
        lines.append(f"🕒 Posted: {e(listing.posted_text)}")
    lines.append(f"👁 First detected: {e(_fmt_time(listing.first_seen_at))}")
    lines.append(f"🔎 Search: {e(search_name)}")
    lines.append(f"👤 Bot Account: {e(account_label)}")
    lines.append("")
    lines.append(f'<a href="{e(listing.url, quote=True)}">Open listing</a>')
    return "\n".join(lines)


def build_client(session: Session, http: Optional[requests.Session] = None, sleep=time.sleep) -> Optional[TelegramClient]:
    token = st.get_secret(session, "telegram_bot_token")
    chat_id = st.get(session, "telegram_chat_id")
    if not token or not chat_id:
        return None
    return TelegramClient(token, chat_id, http=http, sleep=sleep)


def send_test(session: Session, http: Optional[requests.Session] = None, sleep=time.sleep) -> str:
    client = build_client(session, http=http, sleep=sleep)
    if client is None:
        raise TelegramError("Configure the bot token and chat ID first")
    text = ("✅ <b>Marketplace Search Intelligence Bot</b>\n"
            f"Test notification sent at {html.escape(_fmt_time(utcnow()))}.\n"
            "Telegram notifications are configured correctly.")
    return client.send_message(text, disable_preview=True, silent=st.get(session, "telegram_silent"))


def deliver(session: Session, notification: Notification, client: Optional[TelegramClient],
            previous_price_cents: Optional[int] = None) -> bool:
    """Attempt to deliver one notification; updates its row. Returns success."""
    max_attempts = st.get(session, "notification_max_attempts")
    if not st.get(session, "telegram_enabled"):
        notification.status = NotifyStatus.SKIPPED
        notification.last_error = "Telegram notifications disabled"
        return False
    if client is None:
        notification.status = NotifyStatus.FAILED
        notification.last_error = "Telegram not configured"
        notification.next_attempt_at = None
        return False
    listing = notification.listing
    search = notification.search
    account = session.get(Account, notification.account_id) if notification.account_id else None
    text = format_listing_message(listing, search.name if search else "(deleted search)",
                                  account.display_name if account else "—", notification.kind,
                                  previous_price_cents)
    notification.attempts += 1
    try:
        msg_id = client.send_message(text, disable_preview=st.get(session, "telegram_disable_preview"),
                                     silent=st.get(session, "telegram_silent"))
    except TelegramError as exc:
        notification.last_error = str(exc)
        if exc.retryable and notification.attempts < max_attempts:
            notification.status = NotifyStatus.FAILED
            notification.next_attempt_at = datetime.fromtimestamp(
                time.time() + 60 * notification.attempts, tz=timezone.utc).replace(tzinfo=None)
        else:
            notification.status = NotifyStatus.GAVE_UP
            notification.next_attempt_at = None
        log.warning("Telegram delivery failed for notification %s: %s", notification.id, exc)
        return False
    notification.status = NotifyStatus.SENT
    notification.sent_at = utcnow()
    notification.external_id = msg_id
    notification.last_error = None
    return True


def retry_due(session: Session, client_factory=build_client) -> int:
    """Retry failed notifications whose backoff has elapsed. Bounded by attempts."""
    now = utcnow()
    due = session.scalars(select(Notification).where(
        Notification.status == NotifyStatus.FAILED,
        Notification.next_attempt_at.is_not(None),
        Notification.next_attempt_at <= now,
    ).limit(20)).all()
    if not due:
        return 0
    client = client_factory(session)
    sent = 0
    for n in due:
        sent += deliver(session, n, client)
    return sent
