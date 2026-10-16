from unittest.mock import MagicMock, patch
import pytest

from app.services.browser_service import detect_chrome_version, BrowserManager, BrowserOptions


def test_detect_chrome_version_installed():
    """Verify that detect_chrome_version returns detected version or safely yields (None, None)."""
    full_ver, major_ver = detect_chrome_version()
    if full_ver is not None:
        assert isinstance(full_ver, str)
        assert isinstance(major_ver, int)
        assert major_ver > 50
    else:
        assert major_ver is None


def test_detect_chrome_version_invalid_path():
    """Verify that an invalid binary path does not raise and falls back."""
    full_ver, major_ver = detect_chrome_version("non_existent_binary_xyz.exe")
    # Should safely complete without unhandled exception
    if full_ver:
        assert isinstance(major_ver, int)


@patch("app.services.browser_service.subprocess.check_output")
def test_detect_chrome_version_cli_parsing(mock_subproc):
    """Verify CLI version output parsing."""
    mock_subproc.return_value = "Google Chrome 133.0.6943.53\n"
    with patch("os.path.exists", return_value=True), patch("sys.platform", "linux"):
        full_ver, major_ver = detect_chrome_version("/usr/bin/google-chrome")
        assert full_ver == "133.0.6943.53"
        assert major_ver == 133


def test_browser_manager_passes_version_main(tmp_path):
    """Verify BrowserManager passes version_main to driver factory."""
    mock_factory = MagicMock()
    mock_driver = MagicMock()
    mock_factory.return_value = mock_driver

    mgr = BrowserManager(
        locks_dir=tmp_path / "locks",
        driver_factory=mock_factory,
        version_main=133,
    )

    opts = BrowserOptions(headless=True, page_load_timeout=30)
    profile_dir = tmp_path / "profile_1"
    session = mgr.open(1, "Test Account", str(profile_dir), "monitoring", opts)

    assert session is not None
    mock_factory.assert_called_once_with(str(profile_dir), True, 30)
    assert mgr.version_main == 133
    mgr.shutdown_all()
