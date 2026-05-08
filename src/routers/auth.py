"""Auth routes: Steam OpenID, GOG OAuth, PSN NPSSO, Nintendo Switch PKCE, Xbox Live."""
import asyncio
import base64
import hashlib
import http.server
import json
import logging
import os
import socketserver
import threading
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Annotated, Optional
import sys

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from auth import fetch_profile, get_auth_url, verify_callback
from db import load_secrets, save_secrets
from shared import secrets, templates, _URL_LIBRARY, _URL_SETUP, _URL_WIZARD_STEAM_API

logger = logging.getLogger(__name__)

router = APIRouter()

_GOG_REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"

_NINTENDO_PCTL_CLIENT_ID    = "54789befb391a838"
_NINTENDO_PCTL_REDIRECT_URI = f"npf{_NINTENDO_PCTL_CLIENT_ID}://auth"
_NINTENDO_PCTL_SCOPE        = " ".join([
    "openid", "user", "user.mii", "moonUser:administration",
    "moonDevice:create", "moonOwnedDevice:administration",
    "moonParentalControlSetting", "moonParentalControlSetting:update",
    "moonParentalControlSettingState", "moonPairingState",
    "moonSmartDevice:administration", "moonDailySummary", "moonMonthlySummary",
])

_XBOX_CLIENT_ID    = "388ea51c-0b25-4029-aae2-17df49d23905"
_XBOX_REDIRECT_URI = "http://localhost:8080/auth/callback"


def _user(request: Request):
    """Reads _user from main at call time so monkeypatch.setattr(main, '_user', ...) works."""
    return sys.modules["main"]._user(request)


# ---------------------------------------------------------------------------
# Nintendo Switch PKCE helpers
# ---------------------------------------------------------------------------

def _make_switch_auth_url() -> tuple[str, str, str]:
    """Generate a Nintendo PKCE auth URL. Returns (url, state, code_verifier)."""
    state          = base64.urlsafe_b64encode(os.urandom(36)).rstrip(b"=").decode()
    code_verifier  = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    params = urllib.parse.urlencode({
        "state": state,
        "redirect_uri": _NINTENDO_PCTL_REDIRECT_URI,
        "client_id": _NINTENDO_PCTL_CLIENT_ID,
        "scope": _NINTENDO_PCTL_SCOPE,
        "response_type": "session_token_code",
        "session_token_code_challenge": code_challenge,
        "session_token_code_challenge_method": "S256",
        "theme": "login_form",
    })
    url = f"https://accounts.nintendo.com/connect/1.0.0/authorize?{params}"
    return url, state, code_verifier


# ---------------------------------------------------------------------------
# Xbox Live callback server
# ---------------------------------------------------------------------------

async def _xbox_exchange_tokens(code: str) -> None:  # pragma: no cover
    from xbox.webapi.authentication.manager import AuthenticationManager
    from xbox.webapi.common.signed_session import SignedSession

    async with SignedSession() as session:
        auth_mgr = AuthenticationManager(session, _XBOX_CLIENT_ID, "", _XBOX_REDIRECT_URI)
        await auth_mgr.request_tokens(code)
        save_secrets({
            "xbox": {
                "client_id":   _XBOX_CLIENT_ID,
                "oauth":       auth_mgr.oauth.model_dump(mode="json"),
                "user_token":  auth_mgr.user_token.model_dump(mode="json"),
                "xsts_token":  auth_mgr.xsts_token.model_dump(mode="json"),
                "auth_expired": False,
            }
        })


class _XboxCallbackServer(socketserver.TCPServer):  # pragma: no cover
    steampunk_base_url: str


class _XboxCallbackHandler(http.server.BaseHTTPRequestHandler):  # pragma: no cover
    def do_GET(self):
        from typing import cast
        base = cast(_XboxCallbackServer, self.server).steampunk_base_url

        params: dict = {}
        try:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code   = params.get("code", [None])[0]
        except Exception:
            code = None

        if code:
            try:
                asyncio.run(_xbox_exchange_tokens(code))
                redirect_url = f"{base}/setup?xbox_connected=1"
            except Exception as exc:
                logger.error("Xbox token exchange failed: %s", exc)
                redirect_url = f"{base}/setup?error=xbox_token_failed"
        else:
            error = params.get("error_description", params.get("error", ["unknown"]))[0]
            logger.error("Xbox auth callback had no code: %s", error)
            redirect_url = f"{base}/setup?error=xbox_auth_failed"

        body = f'<html><head><meta http-equiv="refresh" content="0;url={redirect_url}"></head></html>'.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # suppress default per-request stdout logging from BaseHTTPRequestHandler


def _run_xbox_callback_server(steampunk_base_url: str) -> None:  # pragma: no cover
    try:
        with _XboxCallbackServer(("127.0.0.1", 8080), _XboxCallbackHandler) as httpd:
            httpd.steampunk_base_url = steampunk_base_url.rstrip("/")
            httpd.timeout = 300
            httpd.handle_request()
    except OSError as exc:
        logger.error("Xbox callback server could not start on port 8080: %s", exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/")
async def login_page(request: Request):
    if _user(request):
        return RedirectResponse(_URL_LIBRARY, status_code=302)
    return templates.TemplateResponse(request, "login.html")


@router.get("/auth/steam")
async def auth_steam(request: Request):
    base = str(request.base_url).rstrip("/")
    return RedirectResponse(
        get_auth_url(return_to=f"{base}/auth/callback", realm=base),
        status_code=302,
    )


@router.get("/auth/callback")
async def auth_callback(request: Request):
    steam_id = verify_callback(dict(request.query_params))
    if not steam_id:
        return RedirectResponse("/?error=auth_failed", status_code=302)

    fresh = load_secrets()
    if not fresh.get("steam", {}).get("api_key"):
        return RedirectResponse(_URL_WIZARD_STEAM_API, status_code=302)

    if fresh["steam"].get("steam_id64") != steam_id:
        save_secrets({"steam": {"steam_id64": steam_id}})
        secrets["steam"]["steam_id64"] = steam_id

    profile = fetch_profile(steam_id, fresh["steam"]["api_key"])
    request.session["user"] = {"steam_id": steam_id, **profile}

    if not fresh["steam"].get("session_cookie"):
        return RedirectResponse("/wizard/steam-cookie", status_code=302)
    return RedirectResponse(_URL_LIBRARY, status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ── GOG ──────────────────────────────────────────────────────────────────────

@router.get("/auth/gog")
async def auth_gog(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    fresh     = load_secrets()
    client_id = fresh.get("gog", {}).get("client_id")
    if not client_id:
        dest = "/wizard/services?error=gog_no_credentials" if request.session.get("wizard_active") else "/setup?error=gog_no_credentials"
        return RedirectResponse(dest, status_code=302)

    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": _GOG_REDIRECT_URI,
        "response_type": "code",
        "layout": "client2",
    })
    return RedirectResponse(f"https://auth.gog.com/auth?{params}", status_code=302)


@router.post("/auth/gog/connect")
async def auth_gog_connect(request: Request, callback_url: Annotated[str, Form()]):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    wizard = request.session.get("wizard_active")

    try:
        parsed = urllib.parse.urlparse(callback_url.strip())
        code   = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
    except Exception:
        code = None

    if not code:
        dest = "/wizard/services?error=gog_no_code" if wizard else "/setup?error=gog_no_code"
        return RedirectResponse(dest, status_code=302)

    fresh = load_secrets()
    gog   = fresh.get("gog", {})

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://auth.gog.com/token",
                data={
                    "client_id":     gog.get("client_id"),
                    "client_secret": gog.get("client_secret"),
                    "grant_type":    "authorization_code",
                    "code":          code,
                    "redirect_uri":  _GOG_REDIRECT_URI,
                },
                timeout=15,
            )
        resp.raise_for_status()
        token_data = resp.json()
    except Exception:
        dest = "/wizard/services?error=gog_token_failed" if wizard else "/setup?error=gog_token_failed"
        return RedirectResponse(dest, status_code=302)

    expires_at = (datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", 3600))).isoformat()
    save_secrets({
        "gog": {
            "access_token":  token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "expires_at":    expires_at,
            "auth_expired":  False,
        }
    })

    if wizard:
        return RedirectResponse("/wizard/services?gog_connected=1", status_code=302)
    return RedirectResponse("/setup?gog_connected=1", status_code=302)


@router.post("/auth/gog/disconnect")
async def auth_gog_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"gog": {"access_token": None, "refresh_token": None, "expires_at": None, "auth_expired": False}})
    return RedirectResponse(_URL_SETUP, status_code=302)


# ── PSN ───────────────────────────────────────────────────────────────────────

@router.post("/auth/psn/connect")
async def auth_psn_connect(request: Request, npsso: Annotated[str, Form()]):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    token  = npsso.strip()
    wizard = request.session.get("wizard_active")
    error_dest = "/wizard/services?error=psn_empty_token" if wizard else "/setup?error=psn_empty_token"

    if not token:
        return RedirectResponse(error_dest, status_code=302)

    npsso_expires_at = None
    if token.startswith("{"):
        try:
            parsed      = json.loads(token)
            expires_in  = parsed.get("expires_in")
            if expires_in:
                npsso_expires_at = (datetime.now(UTC) + timedelta(seconds=int(expires_in))).isoformat()
            token = parsed.get("npsso", token)
        except (AttributeError, ValueError):
            pass
    token = token.strip('"')

    if not token or token.startswith("{"):
        return RedirectResponse(error_dest, status_code=302)

    save_secrets({
        "psn": {
            "npsso":            token,
            "npsso_expires_at": npsso_expires_at,
            "access_token":     None,
            "refresh_token":    None,
            "expires_at":       None,
            "auth_expired":     False,
        }
    })

    if wizard:
        return RedirectResponse("/wizard/services?psn_connected=1", status_code=302)
    return RedirectResponse("/setup?psn_connected=1", status_code=302)


@router.post("/auth/psn/disconnect")
async def auth_psn_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"psn": {"npsso": None, "npsso_expires_at": None, "access_token": None, "refresh_token": None, "expires_at": None, "auth_expired": False}})
    return RedirectResponse(_URL_SETUP, status_code=302)


# ── Nintendo Switch ───────────────────────────────────────────────────────────

@router.get("/auth/switch")
async def auth_switch(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    url, state, code_verifier = _make_switch_auth_url()
    save_secrets({"switch": {"_pkce_state": state, "_pkce_code_verifier": code_verifier}})
    return RedirectResponse(url, status_code=302)


@router.post("/auth/switch/connect")
async def auth_switch_connect(request: Request, redirect_url: Annotated[str, Form()]):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    wizard     = request.session.get("wizard_active")
    error_dest = "/wizard/services?error=switch_no_code" if wizard else "/setup?error=switch_no_code"

    session_token_code: Optional[str] = None
    try:
        parsed = urllib.parse.urlparse(redirect_url.strip())
        for part in (parsed.query, parsed.fragment):
            val = urllib.parse.parse_qs(part).get("session_token_code", [None])[0]
            if val:
                session_token_code = val
                break
    except Exception:
        pass

    if not session_token_code:
        return RedirectResponse(error_dest, status_code=302)

    fresh         = load_secrets()
    code_verifier = fresh.get("switch", {}).get("_pkce_code_verifier")
    if not code_verifier:
        return RedirectResponse(error_dest, status_code=302)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://accounts.nintendo.com/connect/1.0.0/api/session_token",
                headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                data={
                    "client_id":                    _NINTENDO_PCTL_CLIENT_ID,
                    "session_token_code":           session_token_code,
                    "session_token_code_verifier":  code_verifier,
                },
                timeout=15,
            )
        resp.raise_for_status()
        session_token = resp.json().get("session_token")
    except Exception:
        dest = "/wizard/services?error=switch_token_failed" if wizard else "/setup?error=switch_token_failed"
        return RedirectResponse(dest, status_code=302)

    if not session_token:
        dest = "/wizard/services?error=switch_token_failed" if wizard else "/setup?error=switch_token_failed"
        return RedirectResponse(dest, status_code=302)

    save_secrets({
        "switch": {
            "session_token":        session_token,
            "auth_expired":         False,
            "_pkce_state":          None,
            "_pkce_code_verifier":  None,
        }
    })

    if wizard:
        return RedirectResponse("/wizard/services?switch_connected=1", status_code=302)
    return RedirectResponse("/setup?switch_connected=1", status_code=302)


@router.post("/auth/switch/disconnect")
async def auth_switch_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"switch": {"session_token": None, "auth_expired": False}})
    return RedirectResponse(_URL_SETUP, status_code=302)


# ── Xbox Live ─────────────────────────────────────────────────────────────────

@router.get("/auth/xbox")
async def auth_xbox(request: Request):  # pragma: no cover
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    from xbox.webapi.authentication.manager import AuthenticationManager
    from xbox.webapi.common.signed_session import SignedSession

    async with SignedSession() as session:
        auth_mgr  = AuthenticationManager(session, _XBOX_CLIENT_ID, "", _XBOX_REDIRECT_URI)
        auth_url  = auth_mgr.generate_authorization_url()

    base_url = str(request.base_url)
    threading.Thread(target=_run_xbox_callback_server, args=(base_url,), daemon=True).start()
    return RedirectResponse(auth_url, status_code=302)


@router.post("/auth/xbox/disconnect")
async def auth_xbox_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"xbox": {
        "client_id": None, "oauth": None,
        "user_token": None, "xsts_token": None, "auth_expired": False,
    }})
    return RedirectResponse(_URL_SETUP, status_code=302)
