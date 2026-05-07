"""Tests for src/auth.py helpers and src/routers/auth.py routes.

Xbox-specific server code (_xbox_exchange_tokens, _XboxCallbackServer,
_XboxCallbackHandler, _run_xbox_callback_server, auth_xbox) is excluded
via # pragma: no cover because it requires live Xbox credentials and a
real browser redirect.  Everything else is covered here.
"""
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest.py already bootstrapped src/ on sys.path and patched db paths.
import auth as _auth_module
import main as _main_module
from routers.auth import _make_switch_auth_url


def _httpx_mock(json_data: dict):
    """Return a mocked httpx.AsyncClient context manager that yields json_data."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = json_data

    mock_inner = AsyncMock()
    mock_inner.post = AsyncMock(return_value=mock_resp)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


def _httpx_mock_error():
    """Return a mocked httpx.AsyncClient that raises on post."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("HTTP error")

    mock_inner = AsyncMock()
    mock_inner.post = AsyncMock(return_value=mock_resp)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


# ── src/auth.py ───────────────────────────────────────────────────────────────

def test_get_auth_url_targets_steam():
    url = _auth_module.get_auth_url("http://localhost/callback", "http://localhost")
    assert url.startswith("https://steamcommunity.com/openid/login?")


def test_get_auth_url_contains_return_to():
    url = _auth_module.get_auth_url("http://localhost/callback", "http://localhost")
    assert "openid.return_to=" in url


def test_verify_callback_returns_steam_id_on_success():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "ns:http://specs.openid.net/auth/2.0\nis_valid:true\n"
    with patch("auth.requests.post", return_value=mock_resp):
        result = _auth_module.verify_callback({
            "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000001"
        })
    assert result == "76561198000000001"


def test_verify_callback_returns_none_on_http_error():
    mock_resp = MagicMock()
    mock_resp.ok = False
    with patch("auth.requests.post", return_value=mock_resp):
        result = _auth_module.verify_callback({})
    assert result is None


def test_verify_callback_returns_none_when_not_valid():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "is_valid:false\n"
    with patch("auth.requests.post", return_value=mock_resp):
        result = _auth_module.verify_callback({
            "openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000001"
        })
    assert result is None


def test_verify_callback_returns_none_when_claimed_id_absent():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "is_valid:true\n"
    with patch("auth.requests.post", return_value=mock_resp):
        result = _auth_module.verify_callback({})
    assert result is None


def test_verify_callback_returns_none_when_claimed_id_malformed():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "is_valid:true\n"
    with patch("auth.requests.post", return_value=mock_resp):
        result = _auth_module.verify_callback({
            "openid.claimed_id": "https://not-steam.example.com/bad"
        })
    assert result is None


def test_fetch_profile_returns_name_and_avatar():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": {
            "players": [{"personaname": "TestUser", "avatarfull": "https://example.com/avatar.jpg"}]
        }
    }
    with patch("auth.requests.get", return_value=mock_resp):
        result = _auth_module.fetch_profile("76561198000000001", "fake-key")
    assert result == {"name": "TestUser", "avatar": "https://example.com/avatar.jpg"}


def test_fetch_profile_returns_defaults_when_no_players():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": {"players": []}}
    with patch("auth.requests.get", return_value=mock_resp):
        result = _auth_module.fetch_profile("76561198000000001", "fake-key")
    assert result == {"name": "Unknown", "avatar": ""}


def test_fetch_profile_returns_defaults_when_response_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    with patch("auth.requests.get", return_value=mock_resp):
        result = _auth_module.fetch_profile("76561198000000001", "fake-key")
    assert result == {"name": "Unknown", "avatar": ""}


# ── Nintendo PKCE helper ──────────────────────────────────────────────────────

def test_make_switch_auth_url_returns_nintendo_url():
    url, state, code_verifier = _make_switch_auth_url()
    assert url.startswith("https://accounts.nintendo.com/connect/1.0.0/authorize?")
    assert state
    assert code_verifier


def test_make_switch_auth_url_state_differs_each_call():
    _, state1, _ = _make_switch_auth_url()
    _, state2, _ = _make_switch_auth_url()
    assert state1 != state2


# ── Login / Logout ────────────────────────────────────────────────────────────

def test_login_page_authenticated_redirects_to_library(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/library"


def test_login_page_unauthenticated_returns_200(unauth_client):
    response = unauth_client.get("/")
    assert response.status_code == 200


def test_logout_redirects_to_root(client):
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


# ── Steam auth ────────────────────────────────────────────────────────────────

def test_auth_steam_redirects_to_steam_openid(unauth_client):
    response = unauth_client.get("/auth/steam", follow_redirects=False)
    assert response.status_code == 302
    assert "steamcommunity.com/openid/login" in response.headers["location"]


def test_auth_callback_success_redirects_to_library(unauth_client):
    with (
        patch("routers.auth.verify_callback", return_value="76561198000000001"),
        patch("routers.auth.fetch_profile", return_value={"name": "Test", "avatar": ""}),
    ):
        response = unauth_client.get(
            "/auth/callback",
            params={"openid.claimed_id": "https://steamcommunity.com/openid/id/76561198000000001"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert response.headers["location"] == "/library"


def test_auth_callback_failure_redirects_to_error(unauth_client):
    with patch("routers.auth.verify_callback", return_value=None):
        response = unauth_client.get("/auth/callback", follow_redirects=False)
    assert response.status_code == 302
    assert "error=auth_failed" in response.headers["location"]


# ── GOG ──────────────────────────────────────────────────────────────────────

def test_auth_gog_unauthenticated_redirects_to_root(unauth_client):
    response = unauth_client.get("/auth/gog", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_auth_gog_no_client_id_redirects_to_error(client):
    # Fake secrets have gog: {} so client_id is absent
    response = client.get("/auth/gog", follow_redirects=False)
    assert response.status_code == 302
    assert "gog_no_credentials" in response.headers["location"]


def test_auth_gog_with_client_id_redirects_to_gog(client):
    with patch("routers.auth.load_secrets", return_value={"gog": {"client_id": "fake-id"}}):
        response = client.get("/auth/gog", follow_redirects=False)
    assert response.status_code == 302
    assert "auth.gog.com/auth" in response.headers["location"]


def test_auth_gog_connect_no_code_redirects_to_error(client):
    response = client.post(
        "/auth/gog/connect",
        data={"callback_url": "https://embed.gog.com/on_login_success"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "gog_no_code" in response.headers["location"]


def test_auth_gog_connect_success_redirects_with_flag(client):
    mock_cm = _httpx_mock({"access_token": "tok", "refresh_token": "ref", "expires_in": 3600})
    with patch("routers.auth.httpx.AsyncClient", return_value=mock_cm):
        response = client.post(
            "/auth/gog/connect",
            data={"callback_url": "https://embed.gog.com/on_login_success?code=authcode123"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "gog_connected=1" in response.headers["location"]


def test_auth_gog_connect_token_failure_redirects_to_error(client):
    with patch("routers.auth.httpx.AsyncClient", return_value=_httpx_mock_error()):
        response = client.post(
            "/auth/gog/connect",
            data={"callback_url": "https://embed.gog.com/on_login_success?code=authcode123"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "gog_token_failed" in response.headers["location"]


def test_auth_gog_disconnect_redirects_to_setup(client):
    response = client.post("/auth/gog/disconnect", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/setup"


# ── PSN ───────────────────────────────────────────────────────────────────────

def test_auth_psn_connect_unauthenticated_redirects_to_root(unauth_client):
    response = unauth_client.post("/auth/psn/connect", data={"npsso": "token"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_auth_psn_connect_empty_token_redirects_to_error(client):
    response = client.post("/auth/psn/connect", data={"npsso": "  "}, follow_redirects=False)
    assert response.status_code == 302
    assert "psn_empty_token" in response.headers["location"]


def test_auth_psn_connect_plain_token_redirects_with_flag(client):
    response = client.post("/auth/psn/connect", data={"npsso": "myplaintoken"}, follow_redirects=False)
    assert response.status_code == 302
    assert "psn_connected=1" in response.headers["location"]


def test_auth_psn_connect_json_token_parsed(client):
    token_data = json.dumps({"npsso": "actual-npsso-value", "expires_in": 7776000})
    response = client.post("/auth/psn/connect", data={"npsso": token_data}, follow_redirects=False)
    assert response.status_code == 302
    assert "psn_connected=1" in response.headers["location"]


def test_auth_psn_connect_json_without_npsso_key_redirects_to_error(client):
    # JSON has no "npsso" key → token falls back to original JSON string → startswith("{") → error
    token_data = json.dumps({"expires_in": 7776000})
    response = client.post("/auth/psn/connect", data={"npsso": token_data}, follow_redirects=False)
    assert response.status_code == 302
    assert "psn_empty_token" in response.headers["location"]


def test_auth_psn_disconnect_redirects_to_setup(client):
    response = client.post("/auth/psn/disconnect", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/setup"


# ── Nintendo Switch ───────────────────────────────────────────────────────────

def test_auth_switch_unauthenticated_redirects_to_root(unauth_client):
    response = unauth_client.get("/auth/switch", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_auth_switch_redirects_to_nintendo(client):
    response = client.get("/auth/switch", follow_redirects=False)
    assert response.status_code == 302
    assert "accounts.nintendo.com" in response.headers["location"]


def test_auth_switch_connect_no_code_redirects_to_error(client):
    response = client.post(
        "/auth/switch/connect",
        data={"redirect_url": "npf54789befb391a838://auth"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "switch_no_code" in response.headers["location"]


def test_auth_switch_connect_no_verifier_redirects_to_error(client):
    # Force load_secrets to return no verifier regardless of what was written by earlier tests
    with patch("routers.auth.load_secrets", return_value={"switch": {}}):
        response = client.post(
            "/auth/switch/connect",
            data={"redirect_url": "npf54789befb391a838://auth?session_token_code=abc123"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "switch_no_code" in response.headers["location"]


def test_auth_switch_connect_success(client):
    mock_cm = _httpx_mock({"session_token": "nintendo-session-token"})
    with (
        patch("routers.auth.httpx.AsyncClient", return_value=mock_cm),
        patch("routers.auth.load_secrets", return_value={
            "switch": {"_pkce_code_verifier": "test-verifier"}
        }),
    ):
        response = client.post(
            "/auth/switch/connect",
            data={"redirect_url": "npf54789befb391a838://auth?session_token_code=abc123"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "switch_connected=1" in response.headers["location"]


def test_auth_switch_connect_token_failure_redirects_to_error(client):
    with (
        patch("routers.auth.httpx.AsyncClient", return_value=_httpx_mock_error()),
        patch("routers.auth.load_secrets", return_value={
            "switch": {"_pkce_code_verifier": "test-verifier"}
        }),
    ):
        response = client.post(
            "/auth/switch/connect",
            data={"redirect_url": "npf54789befb391a838://auth?session_token_code=abc123"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "switch_token_failed" in response.headers["location"]


def test_auth_switch_disconnect_redirects_to_setup(client):
    response = client.post("/auth/switch/disconnect", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/setup"


# ── Xbox Live ─────────────────────────────────────────────────────────────────

def test_auth_xbox_disconnect_redirects_to_setup(client):
    response = client.post("/auth/xbox/disconnect", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/setup"
