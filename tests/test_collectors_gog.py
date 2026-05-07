"""Tests for src/collectors/gog.py — HTTP calls and file I/O are mocked."""
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

from collectors.gog import (
    _ensure_gog_token,
    _mark_gog_auth_expired,
    fetch_gog_library,
    fetch_gog_product,
    refresh_gog_token,
)


def _mock_resp(ok: bool, json_data=None) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.status_code = 200 if ok else 401
    if json_data is not None:
        r.json.return_value = json_data
    return r


_BASE_SECRETS = {
    "gog": {
        "refresh_token": "old-refresh",
        "client_id": "fake-client-id",
        "client_secret": "fake-secret",
        "access_token": "old-access",
        "auth_expired": False,
    }
}


def _patch_file(initial: dict):
    """Return a context manager that mocks open() to return initial dict on read."""
    return patch("collectors.gog.open", mock_open(read_data=json.dumps(initial)))


# ── refresh_gog_token ─────────────────────────────────────────────────────────

def test_refresh_gog_token_returns_true_on_success():
    new_data = {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}
    secrets = {
        "gog": {
            "refresh_token": "old-refresh",
            "client_id": "cid",
            "client_secret": "sec",
            "access_token": "old",
        }
    }
    with (
        patch("collectors.gog.requests.post", return_value=_mock_resp(True, new_data)),
        _patch_file({"gog": {}}),
        patch("collectors.gog._write_secrets"),
    ):
        result = refresh_gog_token(secrets)
    assert result is True
    assert secrets["gog"]["access_token"] == "new-access"
    assert secrets["gog"]["refresh_token"] == "new-refresh"


def test_refresh_gog_token_returns_false_when_missing_credentials():
    secrets = {"gog": {}}
    result = refresh_gog_token(secrets)
    assert result is False


def test_refresh_gog_token_returns_false_on_http_error():
    secrets = {
        "gog": {"refresh_token": "ref", "client_id": "cid", "client_secret": "sec"}
    }
    with (
        patch("collectors.gog.requests.post", return_value=_mock_resp(False)),
        _patch_file({"gog": {}}),
        patch("collectors.gog._write_secrets"),
    ):
        result = refresh_gog_token(secrets)
    assert result is False
    assert secrets["gog"]["auth_expired"] is True


def test_refresh_gog_token_returns_false_on_request_exception():
    import requests as _r
    secrets = {
        "gog": {"refresh_token": "ref", "client_id": "cid", "client_secret": "sec"}
    }
    with (
        patch("collectors.gog.requests.post", side_effect=_r.RequestException("timeout")),
        _patch_file({"gog": {}}),
        patch("collectors.gog._write_secrets"),
    ):
        result = refresh_gog_token(secrets)
    assert result is False


# ── _mark_gog_auth_expired ────────────────────────────────────────────────────

def test_mark_gog_auth_expired_sets_flag_in_secrets():
    secrets = {"gog": {"auth_expired": False}}
    with (
        _patch_file({"gog": {}}),
        patch("collectors.gog._write_secrets"),
    ):
        _mark_gog_auth_expired(secrets)
    assert secrets["gog"]["auth_expired"] is True


# ── _ensure_gog_token ─────────────────────────────────────────────────────────

def test_ensure_gog_token_returns_none_when_no_access_token():
    result = _ensure_gog_token({"gog": {}})
    assert result is None


def test_ensure_gog_token_returns_token_when_not_expiring():
    expires_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    secrets = {"gog": {"access_token": "valid-token", "expires_at": expires_at}}
    result = _ensure_gog_token(secrets)
    assert result == "valid-token"


def test_ensure_gog_token_refreshes_when_expiring():
    expires_at = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    secrets = {
        "gog": {
            "access_token": "old-token",
            "expires_at": expires_at,
            "refresh_token": "ref",
            "client_id": "cid",
            "client_secret": "sec",
        }
    }
    new_data = {"access_token": "new-token", "refresh_token": "new-ref", "expires_in": 3600}
    with (
        patch("collectors.gog.requests.post", return_value=_mock_resp(True, new_data)),
        _patch_file({"gog": {}}),
        patch("collectors.gog._write_secrets"),
    ):
        result = _ensure_gog_token(secrets)
    assert result == "new-token"


def test_ensure_gog_token_returns_none_when_refresh_fails():
    expires_at = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    secrets = {
        "gog": {
            "access_token": "old-token",
            "expires_at": expires_at,
            "refresh_token": "ref",
            "client_id": "cid",
            "client_secret": "sec",
        }
    }
    with (
        patch("collectors.gog.requests.post", return_value=_mock_resp(False)),
        _patch_file({"gog": {}}),
        patch("collectors.gog._write_secrets"),
    ):
        result = _ensure_gog_token(secrets)
    assert result is None


def test_ensure_gog_token_ignores_bad_expires_at_format():
    secrets = {"gog": {"access_token": "valid-token", "expires_at": "not-a-date"}}
    result = _ensure_gog_token(secrets)
    assert result == "valid-token"


# ── fetch_gog_library ─────────────────────────────────────────────────────────

def test_fetch_gog_library_returns_product_ids():
    mock_resp = _mock_resp(True, {"owned": [111, 222, 333]})
    with patch("collectors.gog.requests.get", return_value=mock_resp):
        result = fetch_gog_library("fake-token")
    assert result == ["111", "222", "333"]


def test_fetch_gog_library_returns_empty_on_http_error():
    mock_resp = _mock_resp(False)
    with patch("collectors.gog.requests.get", return_value=mock_resp):
        result = fetch_gog_library("fake-token")
    assert result == []


# ── fetch_gog_product ─────────────────────────────────────────────────────────

def test_fetch_gog_product_returns_dict_on_success():
    data = {
        "title": "The Witcher 3",
        "images": {"logo2x": "//images.gog.com/witcher3.jpg"},
        "globalReleaseDate": 1433894400,
    }
    mock_resp = _mock_resp(True, data)
    with patch("collectors.gog.requests.get", return_value=mock_resp):
        result = fetch_gog_product("1234567890", "fake-token")
    assert result is not None
    assert result["title"] == "The Witcher 3"
    assert result["cover_url"].startswith("https://")
    assert result["product_id"] == "1234567890"


def test_fetch_gog_product_falls_back_to_logo_when_logo2x_missing():
    data = {
        "title": "Game",
        "images": {"logo": "//images.gog.com/game.jpg"},
        "globalReleaseDate": None,
    }
    mock_resp = _mock_resp(True, data)
    with patch("collectors.gog.requests.get", return_value=mock_resp):
        result = fetch_gog_product("999", "fake-token")
    assert result["cover_url"] == "https://images.gog.com/game.jpg"


def test_fetch_gog_product_returns_none_on_http_error():
    with patch("collectors.gog.requests.get", return_value=_mock_resp(False)):
        result = fetch_gog_product("999", "fake-token")
    assert result is None


def test_fetch_gog_product_handles_no_images():
    data = {"title": "Game", "images": {}, "globalReleaseDate": None}
    mock_resp = _mock_resp(True, data)
    with patch("collectors.gog.requests.get", return_value=mock_resp):
        result = fetch_gog_product("999", "fake-token")
    assert result["cover_url"] is None
