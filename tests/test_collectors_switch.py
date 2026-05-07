"""Tests for src/collectors/switch.py — HTTP calls and file I/O are mocked."""
import json
from unittest.mock import MagicMock, mock_open, patch

from collectors.switch import (
    _ensure_switch_auth,
    _fetch_switch_summaries,
    _get_switch_auth,
    _mark_switch_auth_expired,
    _parse_summaries,
    _pctl_headers,
    fetch_switch_devices,
    fetch_switch_library,
)


def _mock_resp(ok: bool, json_data=None, status_code: int = 200) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.status_code = status_code if ok else status_code
    if json_data is not None:
        r.json.return_value = json_data
    return r


def _patch_file(initial: dict):
    return patch("collectors.switch.open", mock_open(read_data=json.dumps(initial)))


# ── _mark_switch_auth_expired ─────────────────────────────────────────────────

def test_mark_switch_auth_expired_sets_flag():
    secrets = {"switch": {"auth_expired": False}}
    with (
        _patch_file({"switch": {}}),
        patch("collectors.switch._write_secrets"),
    ):
        _mark_switch_auth_expired(secrets)
    assert secrets["switch"]["auth_expired"] is True


# ── _get_switch_auth ──────────────────────────────────────────────────────────

def test_get_switch_auth_returns_auth_dict_on_success():
    token_resp = _mock_resp(True, {"access_token": "na-token"})
    user_resp  = _mock_resp(True, {"id": "user-123"})
    with patch("collectors.switch.requests.post", return_value=token_resp), \
         patch("collectors.switch.requests.get", return_value=user_resp):
        result = _get_switch_auth("session-token-abc")
    assert result == {"access_token": "na-token", "user_id": "user-123"}


def test_get_switch_auth_returns_none_when_token_missing_in_response():
    token_resp = _mock_resp(True, {})
    with patch("collectors.switch.requests.post", return_value=token_resp):
        result = _get_switch_auth("session-token")
    assert result is None


def test_get_switch_auth_returns_none_on_post_exception():
    import requests as _r
    with patch("collectors.switch.requests.post", side_effect=_r.RequestException("timeout")):
        result = _get_switch_auth("session-token")
    assert result is None


def test_get_switch_auth_returns_none_when_user_id_missing():
    token_resp = _mock_resp(True, {"access_token": "na-token"})
    user_resp  = _mock_resp(True, {})
    with patch("collectors.switch.requests.post", return_value=token_resp), \
         patch("collectors.switch.requests.get", return_value=user_resp):
        result = _get_switch_auth("session-token")
    assert result is None


def test_get_switch_auth_returns_none_on_get_exception():
    import requests as _r
    token_resp = _mock_resp(True, {"access_token": "na-token"})
    with patch("collectors.switch.requests.post", return_value=token_resp), \
         patch("collectors.switch.requests.get", side_effect=_r.RequestException("timeout")):
        result = _get_switch_auth("session-token")
    assert result is None


# ── _ensure_switch_auth ───────────────────────────────────────────────────────

def test_ensure_switch_auth_returns_none_when_no_session_token():
    result = _ensure_switch_auth({"switch": {}})
    assert result is None


def test_ensure_switch_auth_returns_auth_on_success():
    auth = {"access_token": "na-token", "user_id": "user-123"}
    with patch("collectors.switch._get_switch_auth", return_value=auth):
        result = _ensure_switch_auth({"switch": {"session_token": "tok"}})
    assert result == auth


def test_ensure_switch_auth_marks_expired_on_failure():
    secrets = {"switch": {"session_token": "tok"}}
    with (
        patch("collectors.switch._get_switch_auth", return_value=None),
        _patch_file({"switch": {}}),
        patch("collectors.switch._write_secrets"),
    ):
        result = _ensure_switch_auth(secrets)
    assert result is None
    assert secrets["switch"]["auth_expired"] is True


# ── _pctl_headers ─────────────────────────────────────────────────────────────

def test_pctl_headers_contains_authorization():
    headers = _pctl_headers("my-token")
    assert headers["Authorization"] == "Bearer my-token"
    assert "X-Moon-App-Id" in headers
    assert "User-Agent" in headers


# ── fetch_switch_devices ──────────────────────────────────────────────────────

def test_fetch_switch_devices_returns_device_ids():
    data = {"items": [{"deviceId": "dev-001"}, {"deviceId": "dev-002"}]}
    with patch("collectors.switch.requests.get", return_value=_mock_resp(True, data)):
        result = fetch_switch_devices("na-token", "user-123")
    assert result == ["dev-001", "dev-002"]


def test_fetch_switch_devices_handles_list_response():
    data = [{"deviceId": "dev-001"}]
    with patch("collectors.switch.requests.get", return_value=_mock_resp(True, data)):
        result = fetch_switch_devices("na-token", "user-123")
    assert result == ["dev-001"]


def test_fetch_switch_devices_returns_empty_on_404():
    with patch("collectors.switch.requests.get", return_value=_mock_resp(False, status_code=404)):
        result = fetch_switch_devices("na-token", "user-123")
    assert result == []


def test_fetch_switch_devices_returns_empty_on_other_error():
    with patch("collectors.switch.requests.get", return_value=_mock_resp(False, status_code=500)):
        result = fetch_switch_devices("na-token", "user-123")
    assert result == []


def test_fetch_switch_devices_returns_empty_on_exception():
    import requests as _r
    with patch("collectors.switch.requests.get", side_effect=_r.RequestException("timeout")):
        result = fetch_switch_devices("na-token", "user-123")
    assert result == []


# ── _parse_summaries ──────────────────────────────────────────────────────────

_MONTHLY_ITEMS = [
    {
        "applications": [
            {
                "applicationId": "0100F2C0115B6000",
                "applicationName": "Zelda TOTK",
                "playingTime": 480,
                "imageUri": "https://img.example.com/totk.jpg",
            }
        ]
    }
]

_DAILY_ITEMS = [
    {
        "dailySummary": {
            "applications": [
                {
                    "applicationId": "0100A3D000129000",
                    "applicationName": "Mario Kart 8",
                    "playingTime": 120,
                    "imageUri": None,
                }
            ]
        }
    }
]


def test_parse_summaries_from_list_items():
    result = _parse_summaries(_MONTHLY_ITEMS, "monthly")
    assert len(result) == 1
    assert result[0]["ns_uid"] == "0100F2C0115B6000"
    assert result[0]["title"] == "Zelda TOTK"
    assert result[0]["play_time_mins"] == 480


def test_parse_summaries_from_daily_summary_key():
    result = _parse_summaries(_DAILY_ITEMS, "daily")
    assert len(result) == 1
    assert result[0]["ns_uid"] == "0100A3D000129000"
    assert result[0]["title"] == "Mario Kart 8"


def test_parse_summaries_returns_empty_when_no_items():
    result = _parse_summaries({}, "empty")
    assert result == []


def test_parse_summaries_skips_entries_without_id_or_title():
    items = [{"applications": [{"playingTime": 10}]}]
    result = _parse_summaries(items, "bad")
    assert result == []


# ── _fetch_switch_summaries ───────────────────────────────────────────────────

def test_fetch_switch_summaries_uses_monthly_data():
    monthly_data = {
        "items": [
            {
                "applications": [
                    {
                        "applicationId": "0100F2C0115B6000",
                        "applicationName": "Zelda",
                        "playingTime": 300,
                    }
                ]
            }
        ]
    }
    by_uid: dict = {}
    with patch("collectors.switch.requests.get", return_value=_mock_resp(True, monthly_data)):
        result = _fetch_switch_summaries("token", "dev-001", by_uid)
    assert result is True
    assert "0100F2C0115B6000" in by_uid


def test_fetch_switch_summaries_returns_false_when_no_data():
    empty_data: dict = {"items": []}
    by_uid: dict = {}
    with patch("collectors.switch.requests.get", return_value=_mock_resp(True, empty_data)):
        result = _fetch_switch_summaries("token", "dev-001", by_uid)
    assert result is False


def test_fetch_switch_summaries_handles_request_exception():
    import requests as _r
    by_uid: dict = {}
    with patch("collectors.switch.requests.get", side_effect=_r.RequestException("timeout")):
        _fetch_switch_summaries("token", "dev-001", by_uid)
    assert by_uid == {}


def test_fetch_switch_summaries_handles_http_error():
    by_uid: dict = {}
    with patch("collectors.switch.requests.get", return_value=_mock_resp(False, status_code=503)):
        _fetch_switch_summaries("token", "dev-001", by_uid)
    assert by_uid == {}


# ── fetch_switch_library ──────────────────────────────────────────────────────

def test_fetch_switch_library_aggregates_across_devices():
    game_data = {
        "items": [
            {
                "applications": [
                    {
                        "applicationId": "0100F2C0115B6000",
                        "applicationName": "Zelda",
                        "playingTime": 300,
                    }
                ]
            }
        ]
    }
    with patch("collectors.switch.requests.get", return_value=_mock_resp(True, game_data)):
        result = fetch_switch_library("token", ["dev-001", "dev-002"])
    # Both devices return the same game; play time should be accumulated
    assert len(result) == 1
    assert result[0]["play_time_mins"] == 600


def test_fetch_switch_library_returns_empty_when_no_devices():
    result = fetch_switch_library("token", [])
    assert result == []
