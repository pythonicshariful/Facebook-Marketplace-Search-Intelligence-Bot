"""Transparent account eligibility & Auto Select engine.

Decision order (each failing check is recorded as a human-readable reason):

1. Account disabled                      -> excluded
2. Session not "Session Ready"           -> excluded (needs login / verification)
3. Profile directory missing             -> excluded
4. Profile locked / busy with a task     -> excluded
5. Needs attention (checkpoint, captcha, restriction) -> excluded (covered by 2)
6. Daily run limit reached               -> excluded
7. Specific assignment                   -> only the assigned account is considered;
                                            never silently replaced by another account
8. Auto Select                           -> only if allowed in settings; picks the
                                            eligible account with an already-open idle
                                            browser, then fewest runs today, then lowest id

Auto Select balances normal workload. It is NOT used to evade limits: when an
account hits a checkpoint/CAPTCHA/restriction/rate limit, the *search itself*
is paused (job_runner), so it is not retried on another account.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, SearchConfiguration, SearchExecution, SessionStatus, utcnow


@dataclass
class SelectionContext:
    profile_exists: Callable[[Account], bool]
    is_locked: Callable[[Account], bool]          # held by another task / external Chrome
    browser_idle_open: Callable[[Account], bool]  # our idle session exists (cheap reuse)
    runs_today: Callable[[Account], int]
    auto_allowed: bool = True


@dataclass
class AccountCheck:
    account_id: int
    name: str
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    runs_today: int = 0
    browser_open: bool = False

    @property
    def why_not(self) -> str:
        return ", ".join(self.reasons)


@dataclass
class SelectionResult:
    account: Optional[Account]
    reason: str
    checks: list[AccountCheck] = field(default_factory=list)


def evaluate_account(acc: Account, ctx: SelectionContext) -> AccountCheck:
    chk = AccountCheck(account_id=acc.id, name=acc.display_name, eligible=False)
    if not acc.enabled:
        chk.reasons.append("disabled")
        return chk
    if acc.session_status != SessionStatus.READY:
        label = {
            SessionStatus.NEEDS_ATTENTION: "requires user intervention (checkpoint/CAPTCHA/restriction)",
            SessionStatus.EXPIRED: "login required",
            SessionStatus.WAITING_LOGIN: "waiting for manual login",
            SessionStatus.NEW: "never logged in",
            SessionStatus.UNVERIFIED: "session not verified",
            SessionStatus.ERROR: "last check failed with an error",
        }.get(acc.session_status, f"session status '{acc.session_status}'")
        chk.reasons.append(label)
        return chk
    if not ctx.profile_exists(acc):
        chk.reasons.append("browser profile directory missing")
        return chk
    if ctx.is_locked(acc):
        chk.reasons.append("profile is in use by another task")
        return chk
    chk.runs_today = ctx.runs_today(acc)
    if acc.daily_run_limit and chk.runs_today >= acc.daily_run_limit:
        chk.reasons.append(f"daily run limit reached ({chk.runs_today}/{acc.daily_run_limit})")
        return chk
    chk.browser_open = ctx.browser_idle_open(acc)
    chk.eligible = True
    return chk


def _ok_phrase(chk: AccountCheck, assigned: bool) -> str:
    parts = []
    if assigned:
        parts.append("it is the account assigned to this search")
    parts += ["its session is valid", "it is enabled", "no other task is using its profile"]
    if chk.browser_open:
        parts.append("its browser is already open and idle")
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def select_account(session: Session, search: SearchConfiguration, ctx: SelectionContext) -> SelectionResult:
    if search.account_mode == "specific":
        acc = session.get(Account, search.account_id) if search.account_id else None
        if acc is None:
            return SelectionResult(None, "No account is assigned to this search. Edit the search and choose an "
                                         "account or Auto Select.")
        chk = evaluate_account(acc, ctx)
        if chk.eligible:
            return SelectionResult(acc, f"{acc.display_name} selected because {_ok_phrase(chk, True)}.", [chk])
        return SelectionResult(None, f"Waiting for assigned account '{acc.display_name}': {chk.why_not}. "
                                     "The search will not be moved to another account.", [chk])

    # Auto Select
    if not ctx.auto_allowed:
        return SelectionResult(None, "Auto Select is disabled in Application Settings. Assign a specific account "
                                     "or enable Auto Select.")
    accounts = session.scalars(select(Account).order_by(Account.id)).all()
    if not accounts:
        return SelectionResult(None, "No accounts are configured. Add an account in Account Manager.")
    checks = [(a, evaluate_account(a, ctx)) for a in accounts]
    eligible = [(a, c) for a, c in checks if c.eligible]
    skipped = "; ".join(f"{c.name}: {c.why_not}" for _, c in checks if not c.eligible)
    if not eligible:
        return SelectionResult(None, f"Auto Select found no eligible account ({skipped}). Search is waiting.",
                               [c for _, c in checks])
    eligible.sort(key=lambda ac: (not ac[1].browser_open, ac[1].runs_today, ac[0].id))
    acc, chk = eligible[0]
    reason = f"{acc.display_name} selected because {_ok_phrase(chk, False)}"
    if len(eligible) > 1:
        reason += f"; it has the fewest runs today ({chk.runs_today})" if not chk.browser_open else ""
    reason += "."
    if skipped:
        reason += f" Not eligible: {skipped}."
    return SelectionResult(acc, reason, [c for _, c in checks])


def runs_today_counter(session: Session) -> Callable[[Account], int]:
    start = datetime.combine(utcnow().date(), time.min)
    rows = session.execute(select(SearchExecution.account_id, func.count()).where(
        SearchExecution.started_at >= start, SearchExecution.account_id.is_not(None),
        SearchExecution.status.in_(["success", "failed", "blocked", "running"]))
        .group_by(SearchExecution.account_id)).all()
    counts = {aid: n for aid, n in rows}
    return lambda acc: counts.get(acc.id, 0)
