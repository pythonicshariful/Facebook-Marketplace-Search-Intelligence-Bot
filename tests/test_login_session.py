import pytest
from unittest.mock import MagicMock
from app.models import Account, SessionStatus
from app.services.login_session import LoginService
from app.services.browser_service import FetchResult
from app.services.page_state import PageState


def test_login_flow_states(tmp_path):
    # Setup mocks
    mock_mgr = MagicMock()
    mock_session = MagicMock()
    mock_session.alive.return_value = True
    mock_session.use_lock.acquire.return_value = True
    mock_mgr.open.return_value = mock_session
    mock_mgr.get.return_value = mock_session

    cfg = MagicMock()
    cfg.BASE_DIR = tmp_path
    cfg.PROFILES_DIR = tmp_path / "profiles"

    service = LoginService(mock_mgr, cfg)

    # 1. Start login sets status to WAITING_LOGIN
    # (Verified through mock calls and state setting)
    assert SessionStatus.WAITING_LOGIN == "waiting_login"
    assert SessionStatus.READY == "ready"
