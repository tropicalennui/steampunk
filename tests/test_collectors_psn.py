"""Tests for src/collectors/psn.py — HTTP calls and file I/O are mocked."""
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, mock_open, patch

from collectors.psn import (
    _NpssoExpired,
    _ensure_psn_token,
    _fetch_psn_trophy_page,
    _mark_psn_auth_expired,
    _psn_token_still_valid,
    exchange_npsso_for_tokens,
    fetch_psn_trophy_titles,
    refresh_psn_token,
)


def _mock_resp(ok: bool, json_data=None, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.status_code = status_code if ok else status_code or 401
    if json_data is not None:
        r.json.return_value = json_data
    return r


def _patch_file(initial: dict):
    return patch("collectors.psn.open", mock_open(read_data=json.dumps(initial)))


# ── exchange_npsso_for_tokens ─────────────────────────────────────────────────

def test_exchange_npsso_returns_token_data_on_success():
    redirect_location = "com.scee.psxandroid.scecompcall://redirect?code=auth123"
    resp1 = MagicMock()
    resp1.headers = {"Location": redirect_location}
    resp1.status_code = 302

    token_data = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
    resp2 = _mock_resp(True, token_data)

    with patch("collectors.psn.requests.get", return_value=resp1), \
         patch("collectors.psn.requests.post", return_value=resp2):
        result = exchange_npsso_for_tokens("fake-npsso")
    assert result == token_data


def test_exchange_npsso_raises_npsso_expired_when_no_code():
    resp1 = MagicMock()
    resp1.headers = {"Location": "https://error.com"}
    resp1.status_code = 200

    import pytest
    with patch("collectors.psn.requests.get", return_value=resp1):
        with pytest.raises(_NpssoExpired):
            exchange_npsso_for_tokens("expired-npsso")


def test_exchange_npsso_returns_none_on_request_exception():
    import requests as _r
    with patch("collectors.psn.requests.get", side_effect=_r.RequestException("timeout")):
        result = exchange_npsso_for_tokens("fake-npsso")
    assert result is None


def test_exchange_npsso_returns_none_when_token_exchange_fails():
    redirect_location = "com.scee.psxandroid.scecompcall://redirect?code=auth123"
    resp1 = MagicMock()
    resp1.headers = {"Location": redirect_location}
    resp1.status_code = 302

    with patch("collectors.psn.requests.get", return_value=resp1), \
         patch("collectors.psn.requests.post", return_value=_mock_resp(False, status_code=400)):
        result = exchange_npsso_for_tokens("fake-npsso")
    assert result is None


# ── refresh_psn_token ─────────────────────────────────────────────────────────

def test_refresh_psn_token_returns_true_on_success():
    secrets = {"psn": {"refresh_token": "old-refresh"}}
    new_data = {"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 3600}
    with (
        patch("collectors.psn.requests.post", return_value=_mock_resp(True, new_data)),
        _patch_file({"psn": {}}),
        patch("collectors.psn._write_secrets"),
    ):
        result = refresh_psn_token(secrets)
    assert result is True
    assert secrets["psn"]["access_token"] == "new-at"


def test_refresh_psn_token_returns_false_when_no_refresh_token():
    secrets = {"psn": {}}
    result = refresh_psn_token(secrets)
    assert result is False


def test_refresh_psn_token_returns_false_on_http_error():
    secrets = {"psn": {"refresh_token": "ref"}}
    with (
        patch("collectors.psn.requests.post", return_value=_mock_resp(False, status_code=401)),
        _patch_file({"psn": {}}),
        patch("collectors.psn._write_secrets"),
    ):
        result = refresh_psn_token(secrets)
    assert result is False
    assert secrets["psn"]["auth_expired"] is True


def test_refresh_psn_token_returns_false_on_request_exception():
    import requests as _r
    secrets = {"psn": {"refresh_token": "ref"}}
    with (
        patch("collectors.psn.requests.post", side_effect=_r.RequestException("timeout")),
        _patch_file({"psn": {}}),
        patch("collectors.psn._write_secrets"),
    ):
        result = refresh_psn_token(secrets)
    assert result is False


# ── _mark_psn_auth_expired ────────────────────────────────────────────────────

def test_mark_psn_auth_expired_sets_flag():
    secrets = {"psn": {"auth_expired": False}}
    with (
        _patch_file({"psn": {}}),
        patch("collectors.psn._write_secrets"),
    ):
        _mark_psn_auth_expired(secrets)
    assert secrets["psn"]["auth_expired"] is True


# ── _psn_token_still_valid ────────────────────────────────────────────────────

def test_psn_token_still_valid_returns_token_when_no_expiry():
    secrets = {"psn": {"access_token": "tok"}}
    result = _psn_token_still_valid(secrets, "tok", "")
    assert result == "tok"


def test_psn_token_still_valid_returns_token_when_not_expiring():
    expires_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    secrets = {"psn": {"access_token": "tok"}}
    result = _psn_token_still_valid(secrets, "tok", expires_at)
    assert result == "tok"


def test_psn_token_still_valid_refreshes_when_expiring():
    expires_at = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    secrets = {"psn": {"access_token": "old-tok", "refresh_token": "ref"}}
    new_data = {"access_token": "new-tok", "refresh_token": "new-ref", "expires_in": 3600}
    with (
        patch("collectors.psn.requests.post", return_value=_mock_resp(True, new_data)),
        _patch_file({"psn": {}}),
        patch("collectors.psn._write_secrets"),
    ):
        result = _psn_token_still_valid(secrets, "old-tok", expires_at)
    assert result == "new-tok"


def test_psn_token_still_valid_ignores_invalid_expiry_format():
    secrets = {"psn": {"access_token": "tok"}}
    result = _psn_token_still_valid(secrets, "tok", "not-a-date")
    assert result == "tok"


# ── _ensure_psn_token ─────────────────────────────────────────────────────────

def test_ensure_psn_token_returns_existing_access_token():
    expires_at = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    secrets = {"psn": {"access_token": "valid-tok", "expires_at": expires_at, "auth_expired": False}}
    result = _ensure_psn_token(secrets)
    assert result == "valid-tok"


def test_ensure_psn_token_returns_none_when_no_npsso():
    secrets = {"psn": {}}
    result = _ensure_psn_token(secrets)
    assert result is None


def test_ensure_psn_token_exchanges_npsso_when_no_access_token():
    redirect = "com.scee.psxandroid.scecompcall://redirect?code=abc"
    resp1 = MagicMock()
    resp1.headers = {"Location": redirect}
    resp1.status_code = 302

    token_data = {"access_token": "fresh-at", "refresh_token": "fresh-rt", "expires_in": 3600}
    resp2 = _mock_resp(True, token_data)

    secrets = {"psn": {"npsso": "valid-npsso"}}
    with (
        patch("collectors.psn.requests.get", return_value=resp1),
        patch("collectors.psn.requests.post", return_value=resp2),
        _patch_file({"psn": {}}),
        patch("collectors.psn._write_secrets"),
    ):
        result = _ensure_psn_token(secrets)
    assert result == "fresh-at"


def test_ensure_psn_token_marks_expired_when_npsso_rejected():
    resp1 = MagicMock()
    resp1.headers = {"Location": "https://error.com"}
    resp1.status_code = 200

    secrets = {"psn": {"npsso": "expired-npsso"}}
    with (
        patch("collectors.psn.requests.get", return_value=resp1),
        _patch_file({"psn": {}}),
        patch("collectors.psn._write_secrets"),
    ):
        result = _ensure_psn_token(secrets)
    assert result is None
    assert secrets["psn"]["auth_expired"] is True


# ── _fetch_psn_trophy_page ────────────────────────────────────────────────────

def test_fetch_psn_trophy_page_returns_data_on_success():
    data = {"trophyTitles": [{"npCommunicationId": "NPWR123"}], "totalItemCount": 1}
    with patch("collectors.psn.requests.get", return_value=_mock_resp(True, data)):
        result = _fetch_psn_trophy_page("fake-token", "trophy", 0)
    assert result == data


def test_fetch_psn_trophy_page_returns_none_on_http_error():
    with patch("collectors.psn.requests.get", return_value=_mock_resp(False, status_code=500)):
        result = _fetch_psn_trophy_page("fake-token", "trophy", 0)
    assert result is None


def test_fetch_psn_trophy_page_returns_none_on_404():
    with patch("collectors.psn.requests.get", return_value=_mock_resp(False, status_code=404)):
        result = _fetch_psn_trophy_page("fake-token", "trophy2", 0)
    assert result is None


def test_fetch_psn_trophy_page_returns_none_on_request_exception():
    import requests as _r
    with patch("collectors.psn.requests.get", side_effect=_r.RequestException("timeout")):
        result = _fetch_psn_trophy_page("fake-token", "trophy", 0)
    assert result is None


# ── fetch_psn_trophy_titles ───────────────────────────────────────────────────

def test_fetch_psn_trophy_titles_returns_all_titles():
    page1 = {"trophyTitles": [{"npCommunicationId": "A"}], "totalItemCount": 1}
    # Return None for the second service endpoint to signal end
    with patch("collectors.psn._fetch_psn_trophy_page", side_effect=[page1, None, None, None]):
        result = fetch_psn_trophy_titles("fake-token")
    assert len(result) == 1
    assert result[0]["npCommunicationId"] == "A"


def test_fetch_psn_trophy_titles_returns_empty_when_all_fail():
    with patch("collectors.psn._fetch_psn_trophy_page", return_value=None):
        result = fetch_psn_trophy_titles("fake-token")
    assert result == []


def test_fetch_psn_trophy_titles_paginates():
    page1 = {"trophyTitles": [{"npCommunicationId": "A"}] * 2, "totalItemCount": 3}
    page2 = {"trophyTitles": [{"npCommunicationId": "B"}], "totalItemCount": 3}
    # PS3/PS4 service: page1 then page2, then PS5 service returns None
    with patch("collectors.psn._fetch_psn_trophy_page", side_effect=[page1, page2, None]):
        result = fetch_psn_trophy_titles("fake-token")
    assert len(result) == 3
