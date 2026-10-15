import pytest
from app.services.page_state import PageState, classify
from tests.fixtures import CHECKPOINT_HTML, MARKETPLACE_RESULTS_HTML, RESTRICTED_HTML


def test_classify_ok_page():
    state, detail = classify("https://www.facebook.com/marketplace/search/?query=civic", MARKETPLACE_RESULTS_HTML)
    assert state == PageState.OK


def test_classify_checkpoint():
    state, detail = classify("https://www.facebook.com/checkpoint/?next=marketplace", CHECKPOINT_HTML)
    assert state == PageState.CHECKPOINT


def test_classify_restricted():
    state, detail = classify("https://www.facebook.com/marketplace/", RESTRICTED_HTML)
    assert state == PageState.RESTRICTED


def test_classify_login_required():
    login_html = '<html><body><form id="login_form"><input name="email"><input name="pass"></form></body></html>'
    state, detail = classify("https://www.facebook.com/login/", login_html, logged_in_cookie=False)
    assert state == PageState.LOGIN_REQUIRED
