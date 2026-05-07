"""Route tests for routers/setup.py and routers/sync.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import main as _main_module


# ── Setup page ────────────────────────────────────────────────────────────────

def test_get_setup_returns_200(client):
    response = client.get("/setup")
    assert response.status_code == 200


def test_post_setup_saves_cookie_and_redirects(client):
    response = client.post("/setup", data={"session_cookie": "new-cookie"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/library"


def test_get_setup_unauthenticated_redirects_to_root(unauth_client):
    response = unauth_client.get("/setup", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


# ── Preferences ───────────────────────────────────────────────────────────────

def test_get_preferences_returns_200(client):
    response = client.get("/preferences")
    assert response.status_code == 200


def test_post_preferences_saves_timezone_and_redirects(client):
    response = client.post(
        "/preferences",
        data={"timezone": "America/New_York"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "preferences" in response.headers["location"]


def test_get_preferences_unauthenticated_redirects(unauth_client):
    response = unauth_client.get("/preferences", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


# ── Wizard routes ─────────────────────────────────────────────────────────────

def test_get_wizard_steam_api_returns_200(client):
    response = client.get("/wizard/steam-api")
    assert response.status_code == 200


def test_post_wizard_steam_api_redirects_to_error_when_invalid(client):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("HTTP error")
    mock_inner = AsyncMock()
    mock_inner.get = AsyncMock(return_value=mock_resp)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    with patch("httpx.AsyncClient", return_value=mock_cm):
        response = client.post(
            "/wizard/steam-api",
            data={"api_key": "fake-key", "vanity_id": "badvanity"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert "error=invalid" in response.headers["location"]


def test_get_wizard_steam_cookie_returns_200(client):
    response = client.get("/wizard/steam-cookie")
    assert response.status_code == 200


def test_post_wizard_steam_cookie_redirects(client):
    response = client.post(
        "/wizard/steam-cookie",
        data={"session_cookie": "my-cookie-value"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/wizard/services"


def test_get_wizard_services_returns_200(client):
    response = client.get("/wizard/services")
    assert response.status_code == 200


def test_post_wizard_complete_redirects_to_library(client):
    response = client.post("/wizard/complete", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/library"


def test_get_wizard_restart_redirects_to_steam_api(client):
    response = client.get("/wizard/restart", follow_redirects=False)
    assert response.status_code == 302
    assert "/wizard/steam-api" in response.headers["location"]


def test_wizard_steam_cookie_unauthenticated_redirects(unauth_client):
    response = unauth_client.get("/wizard/steam-cookie", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


# ── Sync routes ───────────────────────────────────────────────────────────────

def test_post_sync_unauthenticated_redirects(unauth_client):
    response = unauth_client.post("/sync", data={"platforms": "all"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_get_logs_returns_200(client):
    response = client.get("/logs")
    assert response.status_code == 200


def test_get_logs_unauthenticated_redirects(unauth_client):
    response = unauth_client.get("/logs", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def test_post_logs_clear_redirects(client):
    response = client.post("/logs/clear", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/logs"


def test_post_logs_clear_unauthenticated_redirects(unauth_client):
    response = unauth_client.post("/logs/clear", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/"
