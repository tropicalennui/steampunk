"""Setup page, preferences, and first-run wizard routes."""
import sys
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import RedirectResponse

from db import load_secrets, save_secrets
from shared import secrets, templates, _URL_LIBRARY, _URL_SETUP, _URL_WIZARD_STEAM_API

router = APIRouter()


def _user(request: Request):
    return sys.modules["main"]._user(request)


# ---------------------------------------------------------------------------
# Setup & preferences
# ---------------------------------------------------------------------------

@router.get(_URL_SETUP)
async def setup_page(
    request: Request,
    error:           str = "",
    gog_connected:   str = "",
    psn_connected:   str = "",
    switch_connected: str = "",
    xbox_connected:  str = "",
):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    fresh = load_secrets()
    gog   = fresh.get("gog", {})
    psn   = fresh.get("psn", {})
    sw    = fresh.get("switch", {})
    xb    = fresh.get("xbox", {})

    return templates.TemplateResponse(request, "setup.html", {
        "user":              user,
        "error":             error,
        "already_configured": bool(fresh["steam"].get("session_cookie")),
        "gog_connected":     bool(gog.get("access_token") and not gog.get("auth_expired")),
        "gog_auth_expired":  bool(gog.get("auth_expired")),
        "gog_just_connected": bool(gog_connected),
        "psn_connected":     bool(psn.get("npsso") and not psn.get("auth_expired")),
        "psn_auth_expired":  bool(psn.get("auth_expired")),
        "psn_just_connected": bool(psn_connected),
        "psn_npsso_expires_at": psn.get("npsso_expires_at"),
        "switch_connected":  bool(sw.get("session_token") and not sw.get("auth_expired")),
        "switch_auth_expired": bool(sw.get("auth_expired")),
        "switch_just_connected": bool(switch_connected),
        "xbox_connected":    bool(xb.get("oauth") and not xb.get("auth_expired")),
        "xbox_auth_expired": bool(xb.get("auth_expired")),
        "xbox_just_connected": bool(xbox_connected),
    })


@router.post(_URL_SETUP)
async def setup_save(request: Request, session_cookie: Annotated[str, Form()]):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    cookie = session_cookie.strip()
    save_secrets({"steam": {"session_cookie": cookie}})
    secrets["steam"]["session_cookie"] = cookie
    return RedirectResponse(_URL_LIBRARY, status_code=302)


@router.get("/preferences")
async def preferences_page(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "preferences.html", {
        "user":             user,
        "current_timezone": secrets["app"].get("timezone", "UTC"),
    })


@router.post("/preferences")
async def preferences_save(request: Request, timezone: Annotated[str, Form()]):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    tz = timezone.strip()
    save_secrets({"app": {"timezone": tz}})
    secrets["app"]["timezone"]             = tz
    templates.env.globals["timezone"]      = tz
    return RedirectResponse("/preferences?saved=1", status_code=302)


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

@router.get(_URL_WIZARD_STEAM_API)
async def wizard_steam_api(request: Request, error: str = ""):
    fresh = load_secrets()
    steam = fresh.get("steam", {})
    return templates.TemplateResponse(request, "wizard_steam_api.html", {
        "user":      _user(request),
        "error":     error,
        "api_key":   steam.get("api_key", ""),
        "vanity_id": steam.get("vanity_id", ""),
    })


@router.post(_URL_WIZARD_STEAM_API)
async def wizard_steam_api_save(
    request:  Request,
    api_key:  Annotated[str, Form()],
    vanity_id: Annotated[str, Form()],
):
    import httpx as _httpx
    key    = api_key.strip()
    vanity = vanity_id.strip()

    try:
        async with _httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/",
                params={"key": key, "vanityurl": vanity},
                timeout=10,
            )
        resp.raise_for_status()
        data = resp.json().get("response", {})
        if data.get("success") != 1:
            raise ValueError("vanity not resolved")
        steam_id64 = data["steamid"]
    except Exception:
        return RedirectResponse("/wizard/steam-api?error=invalid", status_code=302)

    save_secrets({"steam": {"api_key": key, "vanity_id": vanity, "steam_id64": steam_id64}})
    secrets["steam"]["api_key"]   = key
    secrets["steam"]["vanity_id"] = vanity
    request.session["wizard_active"] = True
    return RedirectResponse("/auth/steam", status_code=302)


@router.get("/wizard/steam-cookie")
async def wizard_steam_cookie(request: Request, error: str = ""):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "wizard_steam_cookie.html", {
        "user":  user,
        "error": error,
    })


@router.post("/wizard/steam-cookie")
async def wizard_steam_cookie_save(request: Request, session_cookie: Annotated[str, Form()]):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    cookie = session_cookie.strip()
    save_secrets({"steam": {"session_cookie": cookie}})
    secrets["steam"]["session_cookie"] = cookie
    return RedirectResponse("/wizard/services", status_code=302)


@router.get("/wizard/services")
async def wizard_services(
    request:          Request,
    gog_connected:    str = "",
    psn_connected:    str = "",
    switch_connected: str = "",
    error:            str = "",
):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    fresh = load_secrets()
    gog   = fresh.get("gog", {})
    psn   = fresh.get("psn", {})
    sw    = fresh.get("switch", {})

    return templates.TemplateResponse(request, "wizard_services.html", {
        "user":              user,
        "error":             error,
        "gog_connected":     bool(gog.get("access_token") and not gog.get("auth_expired")),
        "gog_auth_expired":  bool(gog.get("auth_expired")),
        "gog_just_connected": bool(gog_connected),
        "psn_connected":     bool(psn.get("npsso") and not psn.get("auth_expired")),
        "psn_auth_expired":  bool(psn.get("auth_expired")),
        "psn_just_connected": bool(psn_connected),
        "psn_npsso_expires_at": psn.get("npsso_expires_at"),
        "switch_connected":  bool(sw.get("session_token") and not sw.get("auth_expired")),
        "switch_auth_expired": bool(sw.get("auth_expired")),
        "switch_just_connected": bool(switch_connected),
    })


@router.post("/wizard/complete")
async def wizard_complete(request: Request, background_tasks: BackgroundTasks):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    request.session.pop("wizard_active", None)
    m = sys.modules["main"]
    if not m._sync_running:
        background_tasks.add_task(m._run_sync, None)
    return RedirectResponse(_URL_LIBRARY, status_code=302)


@router.get("/wizard/restart")
async def wizard_restart(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)
    request.session["wizard_active"] = True
    return RedirectResponse(_URL_WIZARD_STEAM_API, status_code=302)
