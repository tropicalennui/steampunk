"""Tests for src/collectors/steam.py fetch helpers (HTTP calls are mocked)."""
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import requests as _requests

from collectors.steam import (
    _fetch_library_xml,
    fetch_achievements,
    fetch_app_details,
    fetch_library,
    fetch_wishlist,
    make_read_session,
    validate_session_cookie,
)


def _mock_resp(ok: bool, json_data=None, text: str = "") -> MagicMock:
    r = MagicMock()
    r.ok = ok
    r.text = text
    if json_data is not None:
        r.json.return_value = json_data
    return r


def _mock_session(ok: bool, json_data=None, text: str = "") -> MagicMock:
    s = MagicMock()
    s.get.return_value = _mock_resp(ok, json_data, text)
    return s


# ── make_read_session ─────────────────────────────────────────────────────────

def test_make_read_session_returns_requests_session():
    session = make_read_session("api-key", "cookie-val")
    assert isinstance(session, _requests.Session)


def test_make_read_session_without_cookie():
    session = make_read_session("api-key")
    assert isinstance(session, _requests.Session)


def test_make_read_session_sets_api_key_param():
    session = make_read_session("my-key")
    assert session.params.get("key") == "my-key"


# ── validate_session_cookie ───────────────────────────────────────────────────

def test_validate_session_cookie_true_when_games_present():
    mock_session = _mock_session(True, {"response": {"games": [{"appid": 570}]}})
    with patch("collectors.steam.make_read_session", return_value=mock_session):
        assert validate_session_cookie("key", "76561198000000001", "cookie") is True


def test_validate_session_cookie_false_when_http_error():
    mock_session = _mock_session(False)
    with patch("collectors.steam.make_read_session", return_value=mock_session):
        assert validate_session_cookie("key", "76561198000000001", "cookie") is False


def test_validate_session_cookie_false_when_no_games_key():
    mock_session = _mock_session(True, {"response": {}})
    with patch("collectors.steam.make_read_session", return_value=mock_session):
        assert validate_session_cookie("key", "76561198000000001", "cookie") is False


# ── fetch_library ─────────────────────────────────────────────────────────────

def test_fetch_library_returns_games_list():
    games = [{"appid": 570, "name": "Dota 2", "playtime_forever": 100}]
    session = _mock_session(True, {"response": {"games": games}})
    session.get.return_value.raise_for_status = MagicMock()
    result = fetch_library(session, "76561198000000001")
    assert result == games


def test_fetch_library_falls_back_to_xml_when_empty():
    xml_text = """<gamesList><games><game>
        <appID>570</appID><name>Dota 2</name>
        <hoursOnRecord>2</hoursOnRecord>
    </game></games></gamesList>"""
    resp_api = MagicMock()
    resp_api.json.return_value = {"response": {"games": []}}
    resp_api.raise_for_status = MagicMock()
    resp_xml = MagicMock()
    resp_xml.ok = True
    resp_xml.text = xml_text
    session = MagicMock()
    session.get.side_effect = [resp_api, resp_xml]
    result = fetch_library(session, "76561198000000001")
    assert len(result) == 1
    assert result[0]["appid"] == 570


# ── _fetch_library_xml ────────────────────────────────────────────────────────

_XML_GAMES = """<?xml version="1.0"?>
<gamesList><games>
    <game>
        <appID>570</appID>
        <name>Dota 2</name>
        <hoursOnRecord>10.5</hoursOnRecord>
        <hoursLast2Weeks>1.0</hoursLast2Weeks>
    </game>
    <game>
        <appID>440</appID>
        <name>Team Fortress 2</name>
        <hoursOnRecord>0</hoursOnRecord>
    </game>
</games></gamesList>"""


def test_fetch_library_xml_parses_games():
    session = _mock_session(True, text=_XML_GAMES)
    result = _fetch_library_xml(session, "76561198000000001")
    assert len(result) == 2
    by_id = {g["appid"]: g for g in result}
    assert by_id[570]["name"] == "Dota 2"
    assert by_id[570]["playtime_forever"] == 630  # 10.5 * 60
    assert by_id[570]["playtime_2weeks"] == 60     # 1.0 * 60


def test_fetch_library_xml_returns_empty_on_http_error():
    session = _mock_session(False, text="")
    result = _fetch_library_xml(session, "76561198000000001")
    assert result == []


def test_fetch_library_xml_returns_empty_on_parse_error():
    session = _mock_session(True, text="<not valid xml")
    result = _fetch_library_xml(session, "76561198000000001")
    assert result == []


def test_fetch_library_xml_skips_games_without_appid():
    xml = "<gamesList><games><game><name>NoID</name></game></games></gamesList>"
    session = _mock_session(True, text=xml)
    result = _fetch_library_xml(session, "76561198000000001")
    assert result == []


def test_fetch_library_xml_returns_empty_on_blank_response():
    session = _mock_session(True, text="   ")
    result = _fetch_library_xml(session, "76561198000000001")
    assert result == []


# ── fetch_app_details ─────────────────────────────────────────────────────────

def test_fetch_app_details_returns_data_on_success():
    data = {"name": "Dota 2", "header_image": "https://example.com/img.jpg"}
    mock_resp = _mock_resp(True, {"570": {"success": True, "data": data}})
    with patch("collectors.steam.requests.get", return_value=mock_resp):
        result = fetch_app_details(570)
    assert result == data


def test_fetch_app_details_returns_none_when_success_false():
    mock_resp = _mock_resp(True, {"570": {"success": False}})
    with patch("collectors.steam.requests.get", return_value=mock_resp):
        result = fetch_app_details(570)
    assert result is None


def test_fetch_app_details_returns_none_on_http_error():
    mock_resp = _mock_resp(False)
    with patch("collectors.steam.requests.get", return_value=mock_resp):
        result = fetch_app_details(570)
    assert result is None


# ── fetch_achievements ────────────────────────────────────────────────────────

def test_fetch_achievements_returns_counts_on_success():
    achievements = [{"achieved": 1}, {"achieved": 0}, {"achieved": 1}]
    session = _mock_session(True, {"playerstats": {"success": True, "achievements": achievements}})
    result = fetch_achievements(session, "76561198000000001", 570)
    assert result == (2, 3, round(2 / 3 * 100, 2))


def test_fetch_achievements_returns_none_on_http_error():
    session = _mock_session(False)
    result = fetch_achievements(session, "76561198000000001", 570)
    assert result is None


def test_fetch_achievements_returns_none_when_success_false():
    session = _mock_session(True, {"playerstats": {"success": False}})
    result = fetch_achievements(session, "76561198000000001", 570)
    assert result is None


def test_fetch_achievements_returns_none_when_no_achievements():
    session = _mock_session(True, {"playerstats": {"success": True, "achievements": []}})
    result = fetch_achievements(session, "76561198000000001", 570)
    assert result is None


def test_fetch_achievements_returns_none_on_request_exception():
    session = MagicMock()
    session.get.side_effect = _requests.RequestException("timeout")
    result = fetch_achievements(session, "76561198000000001", 570)
    assert result is None


# ── fetch_wishlist ────────────────────────────────────────────────────────────

def test_fetch_wishlist_returns_items():
    data = {"570": {"added": 1700000000}, "440": {"added": 1600000000}}
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "non-empty"
    mock_resp.json.return_value = data
    session = MagicMock()
    session.get.return_value = mock_resp
    result = fetch_wishlist(session, "76561198000000001")
    assert len(result) == 2
    app_ids = {item["app_id"] for item in result}
    assert 570 in app_ids
    assert 440 in app_ids


def test_fetch_wishlist_returns_empty_on_http_error():
    session = _mock_session(False, text="")
    result = fetch_wishlist(session, "76561198000000001")
    assert result == []


def test_fetch_wishlist_returns_empty_when_blank_body():
    session = _mock_session(True, text="   ")
    result = fetch_wishlist(session, "76561198000000001")
    assert result == []


def test_fetch_wishlist_returns_empty_when_data_empty():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "non-empty"
    mock_resp.json.return_value = {}
    session = MagicMock()
    session.get.return_value = mock_resp
    result = fetch_wishlist(session, "76561198000000001")
    assert result == []


def test_fetch_wishlist_skips_non_digit_keys():
    data = {"570": {"added": 1700000000}, "not-a-digit": {"added": 0}}
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "non-empty"
    mock_resp.json.return_value = data
    session = MagicMock()
    session.get.return_value = mock_resp
    result = fetch_wishlist(session, "76561198000000001")
    assert len(result) == 1
    assert result[0]["app_id"] == 570
