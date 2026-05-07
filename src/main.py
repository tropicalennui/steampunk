import asyncio
import base64
import hashlib
import http.server
import json
import logging
import os
import socketserver
import subprocess
import sys
import threading
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Optional, Union

import duckdb
import httpx
from fastapi import BackgroundTasks, FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from auth import fetch_profile, get_auth_url, verify_callback
from db import DB_PATH, SECRETS_PATH, init_db, load_secrets, save_secrets

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
SRC_DIR = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs"

_sync_lock = threading.Lock()
_sync_running = False


@contextmanager
def get_db():
    conn = duckdb.connect(str(DB_PATH))
    try:
        yield conn
    finally:
        conn.close()


def _query(conn: duckdb.DuckDBPyConnection, sql: str, params=None) -> list[dict]:
    result = conn.execute(sql, params or [])
    cols = [d[0] for d in result.description]
    return [dict(zip(cols, row)) for row in result.fetchall()]


def _last_synced(conn: duckdb.DuckDBPyConnection) -> str | None:
    rows = _query(conn, "SELECT MAX(collected_at) AS ts FROM stg_steam_library")
    ts = rows[0]["ts"] if rows else None
    if ts is None:
        return None
    return str(ts).replace(" ", "T").split(".")[0] + "Z"


def _user(request: Request) -> dict | None:
    return request.session.get("user")


MAX_LOG_FILES = 10
_LOG_GLOB = "sync_*.log"
_URL_LIBRARY = "/library"
_URL_SETUP = "/setup"
_URL_WIZARD_STEAM_API = "/wizard/steam-api"


def _trim_logs() -> None:
    if not LOGS_DIR.exists():
        return
    for old in sorted(LOGS_DIR.glob(_LOG_GLOB), reverse=True)[MAX_LOG_FILES:]:
        old.unlink(missing_ok=True)


def _run_sync(platforms: list[str] | None = None):
    global _sync_running
    with _sync_lock:
        _sync_running = True
    try:
        LOGS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        log_path = LOGS_DIR / f"sync_{timestamp}.log"
        cmd = [sys.executable, "-u", str(SRC_DIR / "collect.py")]
        if platforms:
            cmd += ["--platforms"] + platforms
        with open(log_path, "w") as log:
            log.write(f"Sync started at {timestamp} UTC\n")
            if platforms:
                log.write(f"Platforms: {', '.join(platforms)}\n")
            log.write(f"{'='*60}\n")
            log.flush()
            subprocess.run(
                cmd,
                cwd=str(SRC_DIR),
                stdout=log,
                stderr=log,
                text=True,
            )
    finally:
        with _sync_lock:
            _sync_running = False
        _trim_logs()


# ---------------------------------------------------------------------------
# Column registry for list-view API
# ---------------------------------------------------------------------------

_GRP_LIB  = "Library data"
_GRP_PLAT = "Platform data"


@dataclass
class ColumnDef:
    label: str
    group: str                          # _GRP_LIB | _GRP_PLAT
    platforms: frozenset                # platform slugs that expose this column
    select_sql: Union[str, dict]        # str, or {platform_slug: sql_fragment}
    join_sql: Union[str, dict, None] = None  # str, or {platform_slug: join_clause}
    default: bool = False


# Canonical aliases used across column defs — deduplication relies on exact string match
_J_STEAM_LIB  = "LEFT JOIN stg_steam_library ssl ON ssl.app_id = TRY_CAST(pg.external_id AS INTEGER)"
_J_STEAM_DET  = "LEFT JOIN stg_steam_app_details sad ON sad.app_id = TRY_CAST(pg.external_id AS INTEGER)"
_J_GOG        = "LEFT JOIN stg_gog_library sgog ON sgog.product_id = pg.external_id"
_J_PSN        = "LEFT JOIN stg_psn_library spsn ON spsn.np_communication_id = pg.external_id"
_J_ACH        = "LEFT JOIN achievements ach ON ach.platform_game_id = pg.id"
_J_REV        = "LEFT JOIN reviews rv ON rv.platform_game_id = pg.id"
_J_GENRES     = "LEFT JOIN game_genres gg ON gg.game_id = g.id LEFT JOIN genres gn ON gn.id = gg.genre_id"
_J_TAGS       = "LEFT JOIN game_tags gt ON gt.game_id = g.id LEFT JOIN tags tg ON tg.id = gt.tag_id"

COLUMN_REGISTRY: dict[str, ColumnDef] = {
    # ── Library data (canonical) ───────────────────────────────────────────────
    "playtime_mins": ColumnDef(
        label="Playtime (total)", group=_GRP_LIB,
        platforms=frozenset({"steam", "switch"}),
        select_sql="MAX(l.playtime_mins) AS playtime_mins",
        default=True,
    ),
    "last_played_at": ColumnDef(
        label="Last played", group=_GRP_LIB,
        platforms=frozenset({"steam"}),
        select_sql="MAX(l.last_played_at) AS last_played_at",
        default=True,
    ),
    "first_played_at": ColumnDef(
        label="First played", group=_GRP_LIB,
        platforms=frozenset({"steam"}),
        select_sql="MAX(l.first_played_at) AS first_played_at",
    ),
    "never_launched": ColumnDef(
        label="Never launched", group=_GRP_LIB,
        platforms=frozenset({"steam"}),
        select_sql="bool_and(l.never_launched) AS never_launched",
    ),
    "purchased_at": ColumnDef(
        label="Purchased at", group=_GRP_LIB,
        platforms=frozenset({"steam", "gog", "psn", "switch"}),
        select_sql="MAX(l.purchased_at) AS purchased_at",
    ),
    "purchase_source": ColumnDef(
        label="Purchase source", group=_GRP_LIB,
        platforms=frozenset({"steam", "gog", "psn", "switch"}),
        select_sql="MAX(l.purchase_source) AS purchase_source",
    ),
    # ── Platform data: Steam ───────────────────────────────────────────────────
    "playtime_2weeks": ColumnDef(
        label="Playtime (last 2 weeks)", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="any_value(ssl.playtime_2weeks_mins) AS playtime_2weeks",
        join_sql=_J_STEAM_LIB,
    ),
    "release_date": ColumnDef(
        label="Release date", group=_GRP_PLAT,
        platforms=frozenset({"steam", "gog"}),
        select_sql={
            "steam": "any_value(sad.release_date) AS release_date",
            "gog":   "CAST(any_value(sgog.release_date) AS VARCHAR) AS release_date",
        },
        join_sql={"steam": _J_STEAM_DET, "gog": _J_GOG},
    ),
    "genres": ColumnDef(
        label="Genres", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="list_distinct(list(gn.name)) FILTER (WHERE gn.name IS NOT NULL) AS genres",
        join_sql=_J_GENRES,
        default=True,
    ),
    "tags": ColumnDef(
        label="Tags", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="list_distinct(list(tg.name)) FILTER (WHERE tg.name IS NOT NULL) AS tags",
        join_sql=_J_TAGS,
    ),
    "steam_categories": ColumnDef(
        label="Steam categories", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="any_value(sad.categories) AS steam_categories",
        join_sql=_J_STEAM_DET,
    ),
    "achievement_pct": ColumnDef(
        label="Achievement %", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="MAX(ach.completion_pct) AS achievement_pct",
        join_sql=_J_ACH,
        default=True,
    ),
    "achievements_count": ColumnDef(
        label="Achievements (earned/total)", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql=(
            "CASE WHEN MAX(ach.total_count) > 0 "
            "THEN CAST(MAX(ach.unlocked_count) AS VARCHAR) || '/' || CAST(MAX(ach.total_count) AS VARCHAR) "
            "ELSE NULL END AS achievements_count"
        ),
        join_sql=_J_ACH,
    ),
    "my_review": ColumnDef(
        label="My review", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="any_value(rv.review_text) AS my_review",
        join_sql=_J_REV,
    ),
    # ── Platform data: PSN ────────────────────────────────────────────────────
    "psn_platform": ColumnDef(
        label="PS Platform (PS4/PS5)", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql="any_value(spsn.platform) AS psn_platform",
        join_sql=_J_PSN,
    ),
    "acquisition_type": ColumnDef(
        label="Acquisition type", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql="any_value(spsn.acquisition_type) AS acquisition_type",
        join_sql=_J_PSN,
    ),
    "trophy_pct": ColumnDef(
        label="Trophy progress %", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql="MAX(spsn.trophy_progress) AS trophy_pct",
        join_sql=_J_PSN,
    ),
    "trophies_count": ColumnDef(
        label="Trophies (earned/defined)", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql=(
            "CASE WHEN MAX(spsn.trophies_defined) > 0 "
            "THEN CAST(MAX(spsn.trophies_earned) AS VARCHAR) || '/' || CAST(MAX(spsn.trophies_defined) AS VARCHAR) "
            "ELSE NULL END AS trophies_count"
        ),
        join_sql=_J_PSN,
    ),
}


def _resolve_col_sql(col: ColumnDef, platform: Optional[str]) -> tuple[str, str]:
    """Return (select_expr, join_clause) resolved for the given platform."""
    sel = col.select_sql if isinstance(col.select_sql, str) else col.select_sql.get(platform or "", "")
    j   = col.join_sql
    if isinstance(j, dict):
        j = j.get(platform or "", "")
    return sel or "", j or ""


def _build_list_query(
    platform: Optional[str],
    col_keys: list[str],
    q: Optional[str],
    show_hidden: bool,
) -> tuple[str, list]:
    selects = [
        "g.id AS game_id",
        "g.title",
        "list_distinct(list(pl.slug)) AS platforms",
        "any_value(ugp.rating) AS rating",
        "COALESCE(any_value(ugp.hidden), FALSE) AS hidden",
    ]
    extra_joins: list[str] = []
    seen_joins: set[str] = set()

    for key in col_keys:
        col = COLUMN_REGISTRY.get(key)
        if col is None or (platform and platform not in col.platforms):
            continue
        sel, j = _resolve_col_sql(col, platform)
        if sel:
            selects.append(sel)
        if j and j not in seen_joins:
            extra_joins.append(j)
            seen_joins.add(j)

    params: list = [show_hidden]
    where_parts = ["(? OR NOT COALESCE(ugp.hidden, FALSE))"]

    if platform:
        where_parts.append("pl.slug = ?")
        params.append(platform)

    if q:
        where_parts.append("lower(g.title) LIKE ?")
        params.append(f"%{q.lower()}%")

    sql = (
        f"SELECT {', '.join(selects)}\n"
        "FROM games g\n"
        "JOIN platform_games pg ON pg.game_id = g.id\n"
        "JOIN platforms pl ON pl.id = pg.platform_id\n"
        "JOIN library l ON l.platform_game_id = pg.id\n"
        "LEFT JOIN user_game_prefs ugp ON ugp.game_id = g.id\n"
        + ("\n".join(extra_joins) + "\n" if extra_joins else "")
        + f"WHERE {' AND '.join(where_parts)}\n"
        "GROUP BY g.id, g.title\n"
        "ORDER BY lower(g.title)"
    )
    return sql, params


# ---------------------------------------------------------------------------
# Pydantic models for preference endpoints
# ---------------------------------------------------------------------------

class RatingBody(BaseModel):
    rating: Optional[str] = None  # 'up' | 'down' | null to clear


class HiddenBody(BaseModel):
    hidden: bool


class MergeBody(BaseModel):
    game_id_a: int
    game_id_b: int
    preferred_title: Optional[str] = None


# ---------------------------------------------------------------------------
# Wizard gate middleware
# ---------------------------------------------------------------------------

class _WizardGate(BaseHTTPMiddleware):
    _OPEN_PREFIXES = ("/wizard", "/auth/", "/static/", "/favicon")

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path == "/" or any(path.startswith(p) for p in self._OPEN_PREFIXES):
            return await call_next(request)
        fresh = load_secrets()
        if not fresh.get("steam", {}).get("api_key"):
            return RedirectResponse(_URL_WIZARD_STEAM_API, status_code=302)
        return await call_next(request)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

secrets = load_secrets()
init_db()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=secrets["app"]["session_secret"])
app.add_middleware(_WizardGate)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["timezone"] = secrets["app"].get("timezone", "UTC")


# ---------------------------------------------------------------------------
# Auth routes — Steam
# ---------------------------------------------------------------------------

@app.get("/")
async def login_page(request: Request):
    if _user(request):
        return RedirectResponse(_URL_LIBRARY, status_code=302)
    return templates.TemplateResponse(request, "login.html")


@app.get("/auth/steam")
async def auth_steam(request: Request):
    base = str(request.base_url).rstrip("/")
    return RedirectResponse(
        get_auth_url(return_to=f"{base}/auth/callback", realm=base),
        status_code=302,
    )


@app.get("/auth/callback")
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


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)


# ---------------------------------------------------------------------------
# Auth routes — GOG
# ---------------------------------------------------------------------------

# GOG's registered redirect URI for the community Galaxy credentials.
# We cannot receive this callback directly, so the user copies the resulting
# URL from their browser and pastes it into the setup form.
_GOG_REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"


@app.get("/auth/gog")
async def auth_gog(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    fresh = load_secrets()
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


@app.post("/auth/gog/connect")
async def auth_gog_connect(request: Request, callback_url: Annotated[str, Form()]):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    wizard = request.session.get("wizard_active")

    try:
        parsed = urllib.parse.urlparse(callback_url.strip())
        code = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
    except Exception:
        code = None

    if not code:
        dest = "/wizard/services?error=gog_no_code" if wizard else "/setup?error=gog_no_code"
        return RedirectResponse(dest, status_code=302)

    fresh = load_secrets()
    gog = fresh.get("gog", {})

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://auth.gog.com/token",
                data={
                    "client_id": gog.get("client_id"),
                    "client_secret": gog.get("client_secret"),
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _GOG_REDIRECT_URI,
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
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "expires_at": expires_at,
            "auth_expired": False,
        }
    })

    if wizard:
        return RedirectResponse("/wizard/services?gog_connected=1", status_code=302)
    return RedirectResponse("/setup?gog_connected=1", status_code=302)


@app.post("/auth/gog/disconnect")
async def auth_gog_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"gog": {"access_token": None, "refresh_token": None, "expires_at": None, "auth_expired": False}})
    return RedirectResponse(_URL_SETUP, status_code=302)


# ---------------------------------------------------------------------------
# Auth routes — PSN
# ---------------------------------------------------------------------------

@app.post("/auth/psn/connect")
async def auth_psn_connect(request: Request, npsso: Annotated[str, Form()]):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    token = npsso.strip()
    wizard = request.session.get("wizard_active")
    error_dest = "/wizard/services?error=psn_empty_token" if wizard else "/setup?error=psn_empty_token"

    if not token:
        return RedirectResponse(error_dest, status_code=302)

    npsso_expires_at = None
    if token.startswith("{"):
        try:
            parsed = json.loads(token)
            expires_in = parsed.get("expires_in")
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
            "npsso": token,
            "npsso_expires_at": npsso_expires_at,
            "access_token": None,
            "refresh_token": None,
            "expires_at": None,
            "auth_expired": False,
        }
    })

    if wizard:
        return RedirectResponse("/wizard/services?psn_connected=1", status_code=302)
    return RedirectResponse("/setup?psn_connected=1", status_code=302)


@app.post("/auth/psn/disconnect")
async def auth_psn_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"psn": {"npsso": None, "npsso_expires_at": None, "access_token": None, "refresh_token": None, "expires_at": None, "auth_expired": False}})
    return RedirectResponse(_URL_SETUP, status_code=302)


# ---------------------------------------------------------------------------
# Auth routes — Nintendo Switch
# ---------------------------------------------------------------------------

_NINTENDO_PCTL_CLIENT_ID = "54789befb391a838"
_NINTENDO_PCTL_REDIRECT_URI = f"npf{_NINTENDO_PCTL_CLIENT_ID}://auth"
_NINTENDO_PCTL_SCOPE = " ".join([
    "openid",
    "user",
    "user.mii",
    "moonUser:administration",
    "moonDevice:create",
    "moonOwnedDevice:administration",
    "moonParentalControlSetting",
    "moonParentalControlSetting:update",
    "moonParentalControlSettingState",
    "moonPairingState",
    "moonSmartDevice:administration",
    "moonDailySummary",
    "moonMonthlySummary",
])


def _make_switch_auth_url() -> tuple[str, str, str]:
    """Generate a Nintendo PKCE auth URL. Returns (url, state, code_verifier)."""
    state = base64.urlsafe_b64encode(os.urandom(36)).rstrip(b"=").decode()
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
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


@app.get("/auth/switch")
async def auth_switch(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    url, state, code_verifier = _make_switch_auth_url()
    save_secrets({"switch": {"_pkce_state": state, "_pkce_code_verifier": code_verifier}})
    return RedirectResponse(url, status_code=302)


@app.post("/auth/switch/connect")
async def auth_switch_connect(request: Request, redirect_url: Annotated[str, Form()]):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    wizard = request.session.get("wizard_active")
    error_dest = "/wizard/services?error=switch_no_code" if wizard else "/setup?error=switch_no_code"

    # Extract session_token_code from the redirect URL (may be in query or fragment)
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

    fresh = load_secrets()
    code_verifier = fresh.get("switch", {}).get("_pkce_code_verifier")
    if not code_verifier:
        return RedirectResponse(error_dest, status_code=302)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://accounts.nintendo.com/connect/1.0.0/api/session_token",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "client_id": _NINTENDO_PCTL_CLIENT_ID,
                    "session_token_code": session_token_code,
                    "session_token_code_verifier": code_verifier,
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
            "session_token": session_token,
            "auth_expired": False,
            "_pkce_state": None,
            "_pkce_code_verifier": None,
        }
    })

    if wizard:
        return RedirectResponse("/wizard/services?switch_connected=1", status_code=302)
    return RedirectResponse("/setup?switch_connected=1", status_code=302)


@app.post("/auth/switch/disconnect")
async def auth_switch_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"switch": {"session_token": None, "auth_expired": False}})
    return RedirectResponse(_URL_SETUP, status_code=302)


# ---------------------------------------------------------------------------
# Auth routes — Xbox Live
# ---------------------------------------------------------------------------

_XBOX_CLIENT_ID = "388ea51c-0b25-4029-aae2-17df49d23905"
_XBOX_REDIRECT_URI = "http://localhost:8080/auth/callback"


async def _xbox_exchange_tokens(code: str) -> None:
    from xbox.webapi.authentication.manager import AuthenticationManager
    from xbox.webapi.common.signed_session import SignedSession

    async with SignedSession() as session:
        auth_mgr = AuthenticationManager(session, _XBOX_CLIENT_ID, "", _XBOX_REDIRECT_URI)
        await auth_mgr.request_tokens(code)
        save_secrets({
            "xbox": {
                "client_id": _XBOX_CLIENT_ID,
                "oauth": auth_mgr.oauth.model_dump(mode="json"),
                "user_token": auth_mgr.user_token.model_dump(mode="json"),
                "xsts_token": auth_mgr.xsts_token.model_dump(mode="json"),
                "auth_expired": False,
            }
        })


class _XboxCallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        base = self.server.steampunk_base_url

        try:
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = params.get("code", [None])[0]
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
        pass


def _run_xbox_callback_server(steampunk_base_url: str) -> None:
    try:
        with socketserver.TCPServer(("127.0.0.1", 8080), _XboxCallbackHandler) as httpd:
            httpd.steampunk_base_url = steampunk_base_url.rstrip("/")
            httpd.timeout = 300
            httpd.handle_request()
    except OSError as exc:
        logger.error("Xbox callback server could not start on port 8080: %s", exc)


@app.get("/auth/xbox")
async def auth_xbox(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    from xbox.webapi.authentication.manager import AuthenticationManager
    from xbox.webapi.common.signed_session import SignedSession

    async with SignedSession() as session:
        auth_mgr = AuthenticationManager(session, _XBOX_CLIENT_ID, "", _XBOX_REDIRECT_URI)
        auth_url = auth_mgr.generate_authorization_url()

    base_url = str(request.base_url)
    threading.Thread(target=_run_xbox_callback_server, args=(base_url,), daemon=True).start()
    return RedirectResponse(auth_url, status_code=302)


@app.post("/auth/xbox/disconnect")
async def auth_xbox_disconnect(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)

    save_secrets({"xbox": {
        "client_id": None, "oauth": None,
        "user_token": None, "xsts_token": None, "auth_expired": False,
    }})
    return RedirectResponse(_URL_SETUP, status_code=302)


# ---------------------------------------------------------------------------
# App routes
# ---------------------------------------------------------------------------

@app.get(_URL_LIBRARY)
async def library(request: Request, show_hidden: bool = False):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    with get_db() as conn:
        last_synced = _last_synced(conn)
        games = _query(conn, """
            SELECT
                cg.id                                                  AS game_id,
                cg.title,
                cg.cover_url,
                list_distinct(list(pl.slug))                           AS platforms,
                MAX(l.playtime_mins)                                   AS playtime_mins,
                MAX(CASE WHEN pl.slug = 'steam'  THEN l.playtime_mins END) AS steam_playtime_mins,
                MAX(CASE WHEN pl.slug = 'switch' THEN l.playtime_mins END) AS switch_playtime_mins,
                bool_and(l.never_launched)                             AS never_launched,
                COALESCE(MAX(a.completion_pct), 0.0)                   AS achievement_pct,
                COALESCE(MAX(spsn.trophy_progress), 0)                 AS trophy_pct,
                bool_or(w.id IS NOT NULL)                              AS on_wishlist,
                list_distinct(list(gn.name))                           AS genres,
                COALESCE(bool_or(sa.platform_id = 1 AND sa.available), FALSE) AS available_on_steam,
                COALESCE(bool_or(sa.platform_id = 3 AND sa.available), FALSE) AS available_on_gog,
                ugp.rating,
                COALESCE(ugp.hidden, FALSE)                            AS hidden
            FROM games g
            JOIN games cg           ON cg.id = COALESCE(g.merged_into, g.id)
            JOIN platform_games pg  ON pg.game_id = g.id
            JOIN platforms pl       ON pl.id = pg.platform_id
            JOIN library l          ON l.platform_game_id = pg.id
            LEFT JOIN achievements a   ON a.platform_game_id = pg.id
            LEFT JOIN wishlist w       ON w.platform_game_id = pg.id
            LEFT JOIN game_genres gg   ON gg.game_id = cg.id
            LEFT JOIN genres gn        ON gn.id = gg.genre_id
            LEFT JOIN store_availability sa ON sa.game_id = cg.id
            LEFT JOIN user_game_prefs ugp   ON ugp.game_id = cg.id
            LEFT JOIN stg_psn_library spsn  ON spsn.np_communication_id = pg.external_id
            WHERE cg.merged_into IS NULL
              AND (? OR NOT COALESCE(ugp.hidden, FALSE))
            GROUP BY cg.id, cg.title, cg.cover_url, ugp.rating, ugp.hidden
            ORDER BY MAX(l.playtime_mins) DESC NULLS LAST
        """, [show_hidden])

    return templates.TemplateResponse(request, "library.html", {
        "user": user,
        "games": games,
        "last_synced": last_synced,
        "sync_running": _sync_running,
        "show_hidden": show_hidden,
    })


@app.get("/profile")
async def profile(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    with get_db() as conn:
        stats = _query(conn, """
            SELECT
                COUNT(DISTINCT g.id)                                         AS total_owned,
                ROUND(SUM(l.playtime_mins) / 60.0, 1)                       AS total_hours,
                SUM(CASE WHEN l.never_launched THEN 1 ELSE 0 END)           AS never_launched
            FROM library l
            JOIN platform_games pg ON pg.id = l.platform_game_id
            JOIN games g            ON g.id  = pg.game_id
        """)[0]

        top_genres = _query(conn, """
            SELECT
                gn.name,
                ROUND(SUM(l.playtime_mins * (1 + COALESCE(a.completion_pct, 0) / 100)) / 60.0, 1)
                    AS weighted_hours
            FROM library l
            JOIN platform_games pg ON pg.id = l.platform_game_id
            JOIN games g            ON g.id  = pg.game_id
            JOIN game_genres gg     ON gg.game_id = g.id
            JOIN genres gn          ON gn.id = gg.genre_id
            LEFT JOIN achievements a ON a.platform_game_id = pg.id
            GROUP BY gn.name
            ORDER BY weighted_hours DESC
            LIMIT 5
        """)

    return templates.TemplateResponse(request, "profile.html", {
        "user": user,
        "stats": stats,
        "top_genres": top_genres,
    })


@app.get(_URL_SETUP)
async def setup_page(
    request: Request,
    error: str = "",
    gog_connected: str = "",
    psn_connected: str = "",
    switch_connected: str = "",
    xbox_connected: str = "",
):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    fresh = load_secrets()
    gog = fresh.get("gog", {})
    psn = fresh.get("psn", {})
    sw = fresh.get("switch", {})
    xb = fresh.get("xbox", {})

    return templates.TemplateResponse(request, "setup.html", {
        "user": user,
        "error": error,
        "already_configured": bool(fresh["steam"].get("session_cookie")),
        "gog_connected": bool(gog.get("access_token") and not gog.get("auth_expired")),
        "gog_auth_expired": bool(gog.get("auth_expired")),
        "gog_just_connected": bool(gog_connected),
        "psn_connected": bool(psn.get("npsso") and not psn.get("auth_expired")),
        "psn_auth_expired": bool(psn.get("auth_expired")),
        "psn_just_connected": bool(psn_connected),
        "psn_npsso_expires_at": psn.get("npsso_expires_at"),
        "switch_connected": bool(sw.get("session_token") and not sw.get("auth_expired")),
        "switch_auth_expired": bool(sw.get("auth_expired")),
        "switch_just_connected": bool(switch_connected),
        "xbox_connected": bool(xb.get("oauth") and not xb.get("auth_expired")),
        "xbox_auth_expired": bool(xb.get("auth_expired")),
        "xbox_just_connected": bool(xbox_connected),
    })


@app.post(_URL_SETUP)
async def setup_save(request: Request, session_cookie: Annotated[str, Form()]):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    cookie = session_cookie.strip()
    save_secrets({"steam": {"session_cookie": cookie}})
    secrets["steam"]["session_cookie"] = cookie
    return RedirectResponse(_URL_LIBRARY, status_code=302)


@app.post("/sync")
async def sync(
    request: Request,
    background_tasks: BackgroundTasks,
    platforms: Annotated[str, Form()] = "all",
):
    if not _user(request):
        return RedirectResponse("/", status_code=302)
    if not _sync_running:
        platform_list = None if platforms == "all" else [p.strip() for p in platforms.split(",")]
        background_tasks.add_task(_run_sync, platform_list)
    return RedirectResponse("/logs", status_code=302)


@app.get("/preferences")
async def preferences_page(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "preferences.html", {
        "user": user,
        "current_timezone": secrets["app"].get("timezone", "UTC"),
    })


@app.post("/preferences")
async def preferences_save(request: Request, timezone: Annotated[str, Form()]):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    tz = timezone.strip()
    save_secrets({"app": {"timezone": tz}})
    secrets["app"]["timezone"] = tz
    templates.env.globals["timezone"] = tz
    return RedirectResponse("/preferences?saved=1", status_code=302)


@app.get("/logs")
async def logs_page(request: Request, file: str = ""):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    log_files = sorted(LOGS_DIR.glob(_LOG_GLOB), reverse=True) if LOGS_DIR.exists() else []
    file_names = [f.name for f in log_files]

    if file in file_names:
        selected = file
    elif file_names:
        selected = file_names[0]
    else:
        selected = None
    lines: list[str] = []
    if selected:
        lines = await asyncio.to_thread(lambda: (LOGS_DIR / selected).read_text().splitlines(True))

    return templates.TemplateResponse(request, "logs.html", {
        "user": user,
        "log_files": file_names,
        "selected": selected,
        "lines": lines,
        "sync_running": _sync_running,
    })


@app.post("/logs/clear")
async def logs_clear(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)
    if not _sync_running and LOGS_DIR.exists():
        for f in LOGS_DIR.glob(_LOG_GLOB):
            f.unlink(missing_ok=True)
    return RedirectResponse("/logs", status_code=302)


# ---------------------------------------------------------------------------
# Library preference endpoints
# ---------------------------------------------------------------------------

@app.put("/library/games/{game_id}/rating")
async def set_rating(request: Request, game_id: int, body: RatingBody):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    rating = body.rating
    if rating not in (None, "up", "down"):
        return JSONResponse({"error": "invalid rating"}, status_code=400)

    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_game_prefs (game_id, rating, updated_at)
            VALUES (?, ?, current_timestamp)
            ON CONFLICT (game_id) DO UPDATE SET
                rating     = excluded.rating,
                updated_at = excluded.updated_at
        """, [game_id, rating])

    return JSONResponse({"game_id": game_id, "rating": rating})


@app.put("/library/games/{game_id}/hidden")
async def set_hidden(request: Request, game_id: int, body: HiddenBody):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_game_prefs (game_id, hidden, updated_at)
            VALUES (?, ?, current_timestamp)
            ON CONFLICT (game_id) DO UPDATE SET
                hidden     = excluded.hidden,
                updated_at = excluded.updated_at
        """, [game_id, body.hidden])

    return JSONResponse({"game_id": game_id, "hidden": body.hidden})


# ---------------------------------------------------------------------------
# List-view API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/library/columns")
async def api_library_columns(request: Request, platform: str = ""):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    if not platform:
        return JSONResponse({"platform": "", "groups": []})

    groups: dict[str, list] = {}
    for key, col in COLUMN_REGISTRY.items():
        if platform not in col.platforms:
            continue
        groups.setdefault(col.group, []).append({
            "key": key,
            "label": col.label,
            "default": col.default,
        })

    return JSONResponse({
        "platform": platform,
        "groups": [{"label": label, "columns": cols} for label, cols in groups.items()],
    })


@app.get("/api/library/games")
async def api_library_games(
    request: Request,
    platform: str = "",
    columns: str = "",
    q: str = "",
    show_hidden: bool = False,
):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    col_keys = [c.strip() for c in columns.split(",") if c.strip()] if columns else []
    sql, params = _build_list_query(platform or None, col_keys, q or None, show_hidden)

    with get_db() as conn:
        rows = _query(conn, sql, params)

    return JSONResponse({"games": rows})


@app.post("/library/games/merge")
async def merge_games(request: Request, body: MergeBody):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    a, b = body.game_id_a, body.game_id_b
    if a == b:
        return JSONResponse({"error": "cannot merge a game with itself"}, status_code=400)

    with get_db() as conn:
        # Determine surviving ID: most platform_games wins; lower id breaks ties
        counts = _query(
            conn,
            "SELECT game_id, COUNT(*) AS n FROM platform_games WHERE game_id IN (?, ?) GROUP BY game_id",
            [a, b],
        )
        count_map = {r["game_id"]: r["n"] for r in counts}
        na, nb = count_map.get(a, 0), count_map.get(b, 0)
        survive = a if na > nb or (na == nb and a < b) else b
        discard = b if survive == a else a

        chosen_title = (body.preferred_title or "").strip() or None

        # Pre-fetch both rows before touching anything
        rows = _query(conn, "SELECT id, title, cover_url, igdb_id FROM games WHERE id IN (?, ?)", [survive, discard])
        if len(rows) < 2:
            return JSONResponse({"error": f"one or both game IDs not found: {a}, {b}"}, status_code=404)
        row_map = {r["id"]: r for r in rows}
        sv, dc = row_map[survive], row_map[discard]

        final_title  = chosen_title or sv["title"]
        final_cover  = sv["cover_url"]  or dc["cover_url"]
        final_igdb   = sv["igdb_id"]    or dc["igdb_id"]

        try:
            conn.execute("BEGIN")

            conn.execute(
                "UPDATE games SET title = ?, cover_url = ?, igdb_id = ? WHERE id = ?",
                [final_title, final_cover, final_igdb, survive],
            )

                # Copy tags/genres/availability/prefs from discard → survive, then clear from discard.
            # platform_games rows are NOT touched — DuckDB FK checks on that table's PK
            # fire even on game_id updates, so we leave platform_games alone entirely.
            # The library query follows merged_into to aggregate both games' platform data.
            conn.execute(
                "INSERT INTO game_tags (game_id, tag_id) SELECT ?, tag_id FROM game_tags WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            conn.execute(
                "INSERT INTO game_genres (game_id, genre_id) SELECT ?, genre_id FROM game_genres WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            conn.execute(
                "INSERT INTO store_availability (game_id, platform_id, available, external_id, checked_at) "
                "SELECT ?, platform_id, available, external_id, checked_at FROM store_availability WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            conn.execute(
                "INSERT INTO user_game_prefs (game_id, rating, hidden, updated_at) "
                "SELECT ?, rating, hidden, updated_at FROM user_game_prefs WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            for table in ("game_tags", "game_genres", "store_availability", "user_game_prefs"):
                conn.execute(f"DELETE FROM {table} WHERE game_id = ?", [discard])

            # Mark discard as merged — library query follows this to produce one card
            conn.execute("UPDATE games SET merged_into = ? WHERE id = ?", [survive, discard])

            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            logger.exception("merge_games failed: survive=%s discard=%s", survive, discard)
            return JSONResponse({"error": "merge failed"}, status_code=500)

    return JSONResponse({"surviving_game_id": survive})


# ---------------------------------------------------------------------------
# Wizard routes
# ---------------------------------------------------------------------------

@app.get(_URL_WIZARD_STEAM_API)
async def wizard_steam_api(request: Request, error: str = ""):
    fresh = load_secrets()
    steam = fresh.get("steam", {})
    return templates.TemplateResponse(request, "wizard_steam_api.html", {
        "user": _user(request),
        "error": error,
        "api_key": steam.get("api_key", ""),
        "vanity_id": steam.get("vanity_id", ""),
    })


@app.post(_URL_WIZARD_STEAM_API)
async def wizard_steam_api_save(
    request: Request,
    api_key: Annotated[str, Form()],
    vanity_id: Annotated[str, Form()],
):
    key = api_key.strip()
    vanity = vanity_id.strip()

    try:
        async with httpx.AsyncClient() as client:
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
    secrets["steam"]["api_key"] = key
    secrets["steam"]["vanity_id"] = vanity
    request.session["wizard_active"] = True
    return RedirectResponse("/auth/steam", status_code=302)


@app.get("/wizard/steam-cookie")
async def wizard_steam_cookie(request: Request, error: str = ""):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "wizard_steam_cookie.html", {
        "user": user,
        "error": error,
    })


@app.post("/wizard/steam-cookie")
async def wizard_steam_cookie_save(request: Request, session_cookie: Annotated[str, Form()]):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    cookie = session_cookie.strip()
    save_secrets({"steam": {"session_cookie": cookie}})
    secrets["steam"]["session_cookie"] = cookie
    return RedirectResponse("/wizard/services", status_code=302)


@app.get("/wizard/services")
async def wizard_services(
    request: Request,
    gog_connected: str = "",
    psn_connected: str = "",
    switch_connected: str = "",
    error: str = "",
):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    fresh = load_secrets()
    gog = fresh.get("gog", {})
    psn = fresh.get("psn", {})
    sw = fresh.get("switch", {})

    return templates.TemplateResponse(request, "wizard_services.html", {
        "user": user,
        "error": error,
        "gog_connected": bool(gog.get("access_token") and not gog.get("auth_expired")),
        "gog_auth_expired": bool(gog.get("auth_expired")),
        "gog_just_connected": bool(gog_connected),
        "psn_connected": bool(psn.get("npsso") and not psn.get("auth_expired")),
        "psn_auth_expired": bool(psn.get("auth_expired")),
        "psn_just_connected": bool(psn_connected),
        "psn_npsso_expires_at": psn.get("npsso_expires_at"),
        "switch_connected": bool(sw.get("session_token") and not sw.get("auth_expired")),
        "switch_auth_expired": bool(sw.get("auth_expired")),
        "switch_just_connected": bool(switch_connected),
    })


@app.post("/wizard/complete")
async def wizard_complete(request: Request, background_tasks: BackgroundTasks):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    request.session.pop("wizard_active", None)
    if not _sync_running:
        background_tasks.add_task(_run_sync, None)
    return RedirectResponse(_URL_LIBRARY, status_code=302)


@app.get("/wizard/restart")
async def wizard_restart(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)
    request.session["wizard_active"] = True
    return RedirectResponse(_URL_WIZARD_STEAM_API, status_code=302)
