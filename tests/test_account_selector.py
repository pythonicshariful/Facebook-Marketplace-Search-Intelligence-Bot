import pytest
from app.models import Account, SearchConfiguration, SessionStatus
from app.services import account_selector as sel


def test_evaluate_account_status():
    acc = Account(
        id=1,
        display_name="Account 1",
        enabled=True,
        session_status=SessionStatus.READY,
        daily_run_limit=10,
    )

    ctx = sel.SelectionContext(
        profile_exists=lambda a: True,
        is_locked=lambda a: False,
        browser_idle_open=lambda a: False,
        runs_today=lambda a: 2,
    )

    chk = sel.evaluate_account(acc, ctx)
    assert chk.eligible is True

    # Test disabled
    acc.enabled = False
    chk_disabled = sel.evaluate_account(acc, ctx)
    assert chk_disabled.eligible is False
    assert "disabled" in chk_disabled.why_not

    # Test needs attention
    acc.enabled = True
    acc.session_status = SessionStatus.NEEDS_ATTENTION
    chk_att = sel.evaluate_account(acc, ctx)
    assert chk_att.eligible is False
    assert "requires user intervention" in chk_att.why_not

    # Test daily limit reached
    acc.session_status = SessionStatus.READY
    ctx_limit = sel.SelectionContext(
        profile_exists=lambda a: True,
        is_locked=lambda a: False,
        browser_idle_open=lambda a: False,
        runs_today=lambda a: 10,
    )
    chk_limit = sel.evaluate_account(acc, ctx_limit)
    assert chk_limit.eligible is False
    assert "daily run limit reached" in chk_limit.why_not


def test_specific_assignment_strictly_respected():
    # If assigned account is not ready, search must wait, not silently switch
    acc1 = Account(id=1, display_name="Account 1", enabled=True, session_status=SessionStatus.NEEDS_ATTENTION)
    search = SearchConfiguration(name="Test Search", account_mode="specific", account_id=1)

    class DummySession:
        def get(self, model, pk):
            return acc1 if pk == 1 else None

    ctx = sel.SelectionContext(
        profile_exists=lambda a: True,
        is_locked=lambda a: False,
        browser_idle_open=lambda a: False,
        runs_today=lambda a: 0,
    )

    res = sel.select_account(DummySession(), search, ctx)
    assert res.account is None
    assert "Waiting for assigned account 'Account 1'" in res.reason
    assert "The search will not be moved to another account" in res.reason
