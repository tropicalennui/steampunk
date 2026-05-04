import json
import time
from datetime import datetime, timedelta, UTC
from typing import Optional
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET

import requests
import duckdb

from db import connect, init_db, load_secrets, SECRETS_PATH

STEAM_API = "https://api.steampowered.com"
STORE_API = "https://store.steampowered.com/api"
WISHLIST_URL = "https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/"

STORE_DELAY = 0.5
ACH_DELAY = 0.3

_STEAM_DOMAINS = [
    "api.steampowered.com",
    "store.steampowered.com",
    "steamcommunity.com",
]

GOG_AUTH_URL = "https://auth.gog.com"
GOG_EMBED_URL = "https://embed.gog.com"
GOG_API_URL = "https://api.gog.com"
GOG_DELAY = 0.5

IGDB_API_URL = "https://api.igdb.com/v4"
IGDB_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_DELAY = 0.25

PSN_AUTH_URL = "https://ca.account.sony.com/api/authz/v3/oauth"
PSN_TROPHY_URL = "https://m.np.playstation.com/api/trophy/v1"
PSN_REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
PSN_SCOPE = "psn:mobile.v2.core psn:clientapp"
# Community-extracted PlayStation mobile app credentials (from psn-api source)
PSN_CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
# Pre-encoded Basic Auth header value: base64(client_id:client_secret)
_PSN_BASIC_AUTH = "MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
PSN_DELAY = 0.5

PLATFORM_STEAM = 1
PLATFORM_PSN = 2
PLATFORM_GOG = 3
PLATFORM_SWITCH = 4
IGDB_STEAM_CATEGORY = 1
IGDB_GOG_CATEGORY = 5
IGDB_PSN_CATEGORY = 36  # PlayStation Store US (was wrong — corrected from IGDB ExternalGameCategoryEnum)

NINTENDO_ACCOUNTS_URL = "https://accounts.nintendo.com"
NINTENDO_NA_USER_URL = "https://api.accounts.nintendo.com/2.0.0/users/me"
NINTENDO_PCTL_CLIENT_ID = "54789befb391a838"  # Nintendo Parental Controls app
NINTENDO_PCTL_URL = "https://api-lp1.pctl.srv.nintendo.net"
NINTENDO_PCTL_APP_ID = "com.nintendo.znma"
NINTENDO_PCTL_APP_VERSION = "2.4.0"
NINTENDO_PCTL_APP_BUILD = "660"
NINTENDO_PCTL_OS_VERSION = "26"
NINTENDO_PCTL_USER_AGENT = f"moon_ANDROID/{NINTENDO_PCTL_APP_VERSION} (com.nintendo.znma; build:{NINTENDO_PCTL_APP_BUILD}; ANDROID {NINTENDO_PCTL_OS_VERSION})"
NINTENDO_DELAY = 0.5
_ACCEPT_JSON = "application/json"


# ---------------------------------------------------------------------------
# Steam — session factory
# ---------------------------------------------------------------------------

def make_read_session(api_key: str, session_cookie: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    session.params = {"key": api_key}  # type: ignore[assignment]
    if session_cookie:
        for domain in _STEAM_DOMAINS:
            session.cookies.set("steamLoginSecure", session_cookie, domain=domain)
    return session


def validate_session_cookie(api_key: str, steam_id: str, session_cookie: str) -> bool:
    session = make_read_session(api_key, session_cookie)
    resp = session.get(
        f"{STEAM_API}/IPlayerService/GetOwnedGames/v1/",
        params={"steamid": steam_id, "include_appinfo": "0"},
        timeout=10,
    )
    if not resp.ok:
        return False
    games = resp.json().get("response", {}).get("games")
    return games is not None


# ---------------------------------------------------------------------------
# Steam — fetch helpers
# ---------------------------------------------------------------------------

def fetch_library(session: requests.Session, steam_id: str) -> list[dict]:
    resp = session.get(
        f"{STEAM_API}/IPlayerService/GetOwnedGames/v1/",
        params={
            "steamid": steam_id,
            "include_appinfo": "1",
            "include_played_free_games": "1",
        },
        timeout=10,
    )
    resp.raise_for_status()
    games = resp.json().get("response", {}).get("games", [])
    if games:
        return games
    print("  API returned 0 games (profile private?) — trying community XML fallback...")
    return _fetch_library_xml(session, steam_id)


def _fetch_library_xml(session: requests.Session, steam_id: str) -> list[dict]:
    resp = session.get(
        f"https://steamcommunity.com/profiles/{steam_id}/games",
        params={"tab": "all", "xml": "1"},
        timeout=15,
    )
    if not resp.ok or not resp.text.strip():
        return []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []
    games = []
    for game in root.findall(".//game"):
        app_id = game.findtext("appID")
        name = game.findtext("name")
        if not app_id or not name:
            continue
        def _mins(tag: str) -> int:
            raw = (game.findtext(tag) or "0").replace(",", "")
            try:
                return int(float(raw) * 60)
            except ValueError:
                return 0
        games.append({
            "appid": int(app_id),
            "name": name,
            "playtime_forever": _mins("hoursOnRecord"),
            "playtime_2weeks": _mins("hoursLast2Weeks") or None,
            "rtime_last_played": None,
        })
    return games


def fetch_app_details(app_id: int) -> Optional[dict]:
    resp = requests.get(
        f"{STORE_API}/appdetails",
        params={"appids": app_id},
        timeout=10,
    )
    if not resp.ok:
        return None
    payload = resp.json().get(str(app_id), {})
    return payload.get("data") if payload.get("success") else None


def fetch_achievements(session: requests.Session, steam_id: str, app_id: int) -> Optional[tuple[int, int, float]]:
    try:
        resp = session.get(
            f"{STEAM_API}/ISteamUserStats/GetPlayerAchievements/v1/",
            params={"steamid": steam_id, "appid": app_id},
            timeout=10,
        )
        if not resp.ok:
            return None
        stats = resp.json().get("playerstats", {})
        if not stats.get("success"):
            return None
        achievements = stats.get("achievements", [])
        if not achievements:
            return None
        total = len(achievements)
        unlocked = sum(1 for a in achievements if a.get("achieved"))
        return unlocked, total, round(unlocked / total * 100, 2)
    except requests.RequestException:
        return None


def fetch_wishlist(session: requests.Session, steam_id: str) -> list[dict]:
    resp = session.get(WISHLIST_URL.format(steam_id=steam_id), timeout=10)
    if not resp.ok or not resp.text.strip():
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    if not data:
        return []
    return [
        {"app_id": int(k), "added_at": v.get("added")}
        for k, v in data.items()
        if k.isdigit()
    ]


# ---------------------------------------------------------------------------
# Steam — stage
# ---------------------------------------------------------------------------

def stage(
    conn: duckdb.DuckDBPyConnection,
    games: list[dict],
    details: dict[int, Optional[dict]],
    achievements: dict[int, tuple[int, int, float]],
    wishlist: list[dict],
) -> None:
    now = datetime.now(UTC)

    if not games:
        return

    conn.executemany(
        """
        INSERT INTO stg_steam_library
            (app_id, name, playtime_forever_mins, playtime_2weeks_mins, last_played_at, collected_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (app_id) DO UPDATE SET
            playtime_forever_mins = excluded.playtime_forever_mins,
            playtime_2weeks_mins  = excluded.playtime_2weeks_mins,
            last_played_at        = excluded.last_played_at,
            collected_at          = excluded.collected_at
        """,
        [
            (
                g["appid"],
                g.get("name", ""),
                g.get("playtime_forever", 0),
                g.get("playtime_2weeks"),
                datetime.fromtimestamp(g["rtime_last_played"], UTC)
                    if g.get("rtime_last_played") else None,
                now,
            )
            for g in games
        ],
    )

    detail_rows = [
        (
            app_id,
            d.get("name", ""),
            [g["description"] for g in d.get("genres", [])],
            [],
            [c["description"] for c in d.get("categories", [])],
            [str(i) for i in d.get("content_descriptors", {}).get("ids", [])],
            d.get("header_image"),
            d.get("release_date", {}).get("date"),
            now,
        )
        for app_id, d in details.items()
        if d is not None
    ]
    if detail_rows:
        conn.executemany(
            """
            INSERT INTO stg_steam_app_details
                (app_id, name, genres, tags, categories, content_descriptors,
                 header_image, release_date, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (app_id) DO UPDATE SET
                name                = excluded.name,
                genres              = excluded.genres,
                tags                = excluded.tags,
                categories          = excluded.categories,
                content_descriptors = excluded.content_descriptors,
                header_image        = excluded.header_image,
                release_date        = excluded.release_date,
                collected_at        = excluded.collected_at
            """,
            detail_rows,
        )

    ach_rows = [(app_id, u, t, p, now) for app_id, (u, t, p) in achievements.items()]
    if ach_rows:
        conn.executemany(
            """
            INSERT INTO stg_steam_achievements
                (app_id, unlocked_count, total_count, completion_pct, collected_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (app_id) DO UPDATE SET
                unlocked_count = excluded.unlocked_count,
                total_count    = excluded.total_count,
                completion_pct = excluded.completion_pct,
                collected_at   = excluded.collected_at
            """,
            ach_rows,
        )

    wish_rows = [
        (
            item["app_id"],
            datetime.fromtimestamp(item["added_at"], UTC) if item.get("added_at") else None,
            now,
        )
        for item in wishlist
    ]
    if wish_rows:
        conn.executemany(
            """
            INSERT INTO stg_steam_wishlist (app_id, added_at, collected_at)
            VALUES (?, ?, ?)
            ON CONFLICT (app_id) DO UPDATE SET
                added_at     = excluded.added_at,
                collected_at = excluded.collected_at
            """,
            wish_rows,
        )


# ---------------------------------------------------------------------------
# Steam — promote staging → canonical
# ---------------------------------------------------------------------------

def promote(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        INSERT INTO games (title, cover_url)
        SELECT sl.name, ad.header_image
        FROM stg_steam_library sl
        LEFT JOIN stg_steam_app_details ad ON ad.app_id = sl.app_id
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 1
              AND pg.external_id = CAST(sl.app_id AS VARCHAR)
        )
    """)

    conn.execute("""
        INSERT INTO platform_games (platform_id, external_id, game_id)
        SELECT 1, CAST(sl.app_id AS VARCHAR), g.id
        FROM stg_steam_library sl
        JOIN games g ON g.title = sl.name
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 1
              AND pg.external_id = CAST(sl.app_id AS VARCHAR)
        )
        ON CONFLICT DO NOTHING
    """)

    conn.execute("""
        INSERT INTO library
            (platform_game_id, playtime_mins, last_played_at, never_launched, collected_at)
        SELECT pg.id, sl.playtime_forever_mins, sl.last_played_at,
               sl.playtime_forever_mins = 0, sl.collected_at
        FROM stg_steam_library sl
        JOIN platform_games pg
          ON pg.platform_id = 1 AND pg.external_id = CAST(sl.app_id AS VARCHAR)
        ON CONFLICT (platform_game_id) DO UPDATE SET
            playtime_mins  = excluded.playtime_mins,
            last_played_at = excluded.last_played_at,
            never_launched = excluded.never_launched,
            collected_at   = excluded.collected_at
    """)

    conn.execute("""
        INSERT INTO genres (name)
        SELECT DISTINCT unnest(genres) FROM stg_steam_app_details
        WHERE genres IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    conn.execute("""
        INSERT INTO game_genres (game_id, genre_id)
        SELECT DISTINCT pg.game_id, gn.id
        FROM (
            SELECT app_id, unnest(genres) AS genre_name
            FROM stg_steam_app_details WHERE genres IS NOT NULL
        ) ad
        JOIN platform_games pg
          ON pg.platform_id = 1 AND pg.external_id = CAST(ad.app_id AS VARCHAR)
        JOIN genres gn ON gn.name = ad.genre_name
        ON CONFLICT DO NOTHING
    """)

    conn.execute("""
        INSERT INTO achievements
            (platform_game_id, unlocked_count, total_count, completion_pct, collected_at)
        SELECT pg.id, sa.unlocked_count, sa.total_count, sa.completion_pct, sa.collected_at
        FROM stg_steam_achievements sa
        JOIN platform_games pg
          ON pg.platform_id = 1 AND pg.external_id = CAST(sa.app_id AS VARCHAR)
        ON CONFLICT (platform_game_id) DO UPDATE SET
            unlocked_count = excluded.unlocked_count,
            total_count    = excluded.total_count,
            completion_pct = excluded.completion_pct,
            collected_at   = excluded.collected_at
    """)

    conn.execute("""
        INSERT INTO wishlist (platform_game_id, added_at, collected_at)
        SELECT pg.id, sw.added_at, sw.collected_at
        FROM stg_steam_wishlist sw
        JOIN platform_games pg
          ON pg.platform_id = 1 AND pg.external_id = CAST(sw.app_id AS VARCHAR)
        ON CONFLICT (platform_game_id) DO UPDATE SET
            added_at     = excluded.added_at,
            collected_at = excluded.collected_at
    """)


# ---------------------------------------------------------------------------
# GOG — token management
# ---------------------------------------------------------------------------

def _write_secrets(data: dict) -> None:
    with open(SECRETS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def refresh_gog_token(secrets: dict) -> bool:
    """Refresh the GOG access token in-place and persist to gandalf.json.
    Returns True on success, False on failure (sets auth_expired flag on failure)."""
    gog = secrets.get("gog", {})
    refresh_token = gog.get("refresh_token")
    client_id = gog.get("client_id")
    client_secret = gog.get("client_secret")

    if not all([refresh_token, client_id, client_secret]):
        return False

    try:
        resp = requests.post(
            f"{GOG_AUTH_URL}/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"  GOG token refresh request failed: {e}")
        _mark_gog_auth_expired(secrets)
        return False

    if not resp.ok:
        print(f"  GOG token refresh failed: HTTP {resp.status_code}")
        _mark_gog_auth_expired(secrets)
        return False

    data = resp.json()
    new_access = data.get("access_token")
    new_refresh = data.get("refresh_token", refresh_token)
    expires_in = data.get("expires_in", 3600)

    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("gog", {})
    persisted["gog"]["access_token"] = new_access
    persisted["gog"]["refresh_token"] = new_refresh
    persisted["gog"]["expires_at"] = (
        datetime.now(UTC) + timedelta(seconds=expires_in)
    ).isoformat()
    persisted["gog"]["auth_expired"] = False
    _write_secrets(persisted)

    secrets["gog"]["access_token"] = new_access
    secrets["gog"]["refresh_token"] = new_refresh
    secrets["gog"]["auth_expired"] = False
    return True


def _mark_gog_auth_expired(secrets: dict) -> None:
    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("gog", {})
    persisted["gog"]["auth_expired"] = True
    _write_secrets(persisted)
    secrets.setdefault("gog", {})
    secrets["gog"]["auth_expired"] = True


def _ensure_gog_token(secrets: dict) -> Optional[str]:
    """Return a valid GOG access token, refreshing if needed. Returns None if unavailable."""
    gog = secrets.get("gog", {})
    access_token = gog.get("access_token")
    expires_at_str = gog.get("expires_at")

    if not access_token:
        return None

    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now(UTC) >= expires_at - timedelta(seconds=60):
                print("  GOG token expiring — refreshing...")
                if not refresh_gog_token(secrets):
                    return None
                access_token = secrets["gog"]["access_token"]
        except ValueError:
            pass

    return access_token


# ---------------------------------------------------------------------------
# GOG — fetch helpers
# ---------------------------------------------------------------------------

def fetch_gog_library(access_token: str) -> list[str]:
    """Return list of GOG product IDs owned by the authenticated user."""
    resp = requests.get(
        f"{GOG_EMBED_URL}/user/data/games",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if not resp.ok:
        print(f"  GOG library fetch failed: HTTP {resp.status_code}")
        return []
    return [str(pid) for pid in resp.json().get("owned", [])]


def fetch_gog_product(product_id: str, access_token: str) -> Optional[dict]:
    """Return title, cover_url and release_date for a GOG product."""
    resp = requests.get(
        f"{GOG_API_URL}/products/{product_id}",
        params={"expand": "description"},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if not resp.ok:
        return None
    data = resp.json()
    images = data.get("images", {})
    cover = images.get("logo2x") or images.get("logo")
    if cover and cover.startswith("//"):
        cover = "https:" + cover

    release_date = None
    release_ts = data.get("globalReleaseDate")
    if release_ts:
        try:
            release_date = datetime.fromtimestamp(release_ts, UTC).date()
        except (OSError, OverflowError):
            pass

    return {
        "product_id": str(product_id),
        "title": data.get("title", ""),
        "cover_url": cover,
        "release_date": release_date,
    }


# ---------------------------------------------------------------------------
# GOG — stage
# ---------------------------------------------------------------------------

def stage_gog(conn: duckdb.DuckDBPyConnection, products: list[dict]) -> None:
    if not products:
        return
    now = datetime.now(UTC)
    conn.executemany(
        """
        INSERT INTO stg_gog_library (product_id, title, cover_url, release_date, collected_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (product_id) DO UPDATE SET
            title        = excluded.title,
            cover_url    = excluded.cover_url,
            release_date = excluded.release_date,
            collected_at = excluded.collected_at
        """,
        [
            (p["product_id"], p["title"], p["cover_url"], p["release_date"], now)
            for p in products
        ],
    )


# ---------------------------------------------------------------------------
# GOG — promote staging → canonical
# ---------------------------------------------------------------------------

def promote_gog(conn: duckdb.DuckDBPyConnection) -> None:
    # For each GOG product not yet in platform_games:
    # re-use an existing games row (by exact title) if one exists, otherwise create a new one.
    conn.execute("""
        INSERT INTO games (title, cover_url)
        SELECT sg.title, sg.cover_url
        FROM stg_gog_library sg
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 3 AND pg.external_id = sg.product_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM games g WHERE g.title = sg.title
        )
    """)

    conn.execute("""
        INSERT INTO platform_games (platform_id, external_id, game_id)
        SELECT 3, sg.product_id, g.id
        FROM stg_gog_library sg
        JOIN games g ON g.title = sg.title
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 3 AND pg.external_id = sg.product_id
        )
        ON CONFLICT DO NOTHING
    """)

    # GOG has no playtime; store 0 (playtime is suppressed in UI for GOG-only games)
    conn.execute("""
        INSERT INTO library (platform_game_id, playtime_mins, last_played_at, never_launched, collected_at)
        SELECT pg.id, 0, NULL, FALSE, sg.collected_at
        FROM stg_gog_library sg
        JOIN platform_games pg
          ON pg.platform_id = 3 AND pg.external_id = sg.product_id
        ON CONFLICT (platform_game_id) DO UPDATE SET
            collected_at = excluded.collected_at
    """)


# ---------------------------------------------------------------------------
# PSN — token management
# ---------------------------------------------------------------------------

class _NpssoExpired(Exception):
    pass


def exchange_npsso_for_tokens(npsso: str) -> Optional[dict]:
    """Exchange an NPSSO cookie for PSN OAuth access + refresh tokens.
    Raises _NpssoExpired if Sony rejects the NPSSO (session genuinely gone)."""
    try:
        resp = requests.get(
            f"{PSN_AUTH_URL}/authorize",
            params={
                "access_type": "offline",
                "client_id": PSN_CLIENT_ID,
                "redirect_uri": PSN_REDIRECT_URI,
                "response_type": "code",
                "scope": PSN_SCOPE,
            },
            headers={"Cookie": f"npsso={npsso}"},
            allow_redirects=False,
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"  PSN NPSSO exchange request failed: {e}")
        return None

    location = resp.headers.get("Location", "")
    code = parse_qs(urlparse(location).query).get("code", [None])[0]
    if not code:
        print(f"  PSN NPSSO exchange: no auth code in redirect (status={resp.status_code}, location={location[:120]})")
        raise _NpssoExpired

    try:
        resp2 = requests.post(
            f"{PSN_AUTH_URL}/token",
            data={
                "code": code,
                "redirect_uri": PSN_REDIRECT_URI,
                "grant_type": "authorization_code",
                "token_format": "jwt",
            },
            headers={"Authorization": f"Basic {_PSN_BASIC_AUTH}"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"  PSN token exchange request failed: {e}")
        return None

    if not resp2.ok:
        print(f"  PSN token exchange failed: HTTP {resp2.status_code} — {resp2.text[:200]}")
        return None

    return resp2.json()


def refresh_psn_token(secrets: dict) -> bool:
    """Refresh the PSN access token in-place and persist to gandalf.json.
    Returns True on success, False on failure (sets auth_expired flag on failure)."""
    psn = secrets.get("psn", {})
    refresh_token = psn.get("refresh_token")

    if not refresh_token:
        return False

    try:
        resp = requests.post(
            f"{PSN_AUTH_URL}/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": PSN_SCOPE,
                "token_format": "jwt",
            },
            headers={"Authorization": f"Basic {_PSN_BASIC_AUTH}"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"  PSN token refresh request failed: {e}")
        _mark_psn_auth_expired(secrets)
        return False

    if not resp.ok:
        print(f"  PSN token refresh failed: HTTP {resp.status_code}")
        _mark_psn_auth_expired(secrets)
        return False

    data = resp.json()
    new_access = data.get("access_token")
    new_refresh = data.get("refresh_token", refresh_token)
    expires_in = data.get("expires_in", 3600)

    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("psn", {})
    persisted["psn"]["access_token"] = new_access
    persisted["psn"]["refresh_token"] = new_refresh
    persisted["psn"]["expires_at"] = (
        datetime.now(UTC) + timedelta(seconds=expires_in)
    ).isoformat()
    persisted["psn"]["auth_expired"] = False
    _write_secrets(persisted)

    secrets["psn"]["access_token"] = new_access
    secrets["psn"]["refresh_token"] = new_refresh
    secrets["psn"]["auth_expired"] = False
    return True


def _mark_psn_auth_expired(secrets: dict) -> None:
    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("psn", {})
    persisted["psn"]["auth_expired"] = True
    _write_secrets(persisted)
    secrets.setdefault("psn", {})
    secrets["psn"]["auth_expired"] = True


def _psn_token_still_valid(secrets: dict, access_token: str, expires_at_str: str) -> Optional[str]:
    """Return a current token (refreshing if near expiry), or None if refresh failed."""
    if not expires_at_str:
        return access_token
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now(UTC) >= expires_at - timedelta(seconds=60):
            print("  PSN token expiring — refreshing...")
            if not refresh_psn_token(secrets):
                return None
            return secrets["psn"]["access_token"]
    except ValueError:
        pass
    return access_token


def _ensure_psn_token(secrets: dict) -> Optional[str]:
    """Return a valid PSN access token, exchanging NPSSO or refreshing as needed."""
    psn = secrets.get("psn", {})
    # Clear a stale auth_expired flag so we always try — only re-set it if Sony
    # explicitly rejects the NPSSO (i.e. _NpssoExpired is raised below).
    if psn.get("auth_expired"):
        psn["auth_expired"] = False

    access_token = psn.get("access_token")
    if access_token:
        return _psn_token_still_valid(secrets, access_token, psn.get("expires_at", ""))

    # No access token — try to exchange NPSSO
    npsso = psn.get("npsso")
    if not npsso:
        return None

    print("  Exchanging PSN NPSSO for OAuth tokens...")
    try:
        token_data = exchange_npsso_for_tokens(npsso)
    except _NpssoExpired:
        _mark_psn_auth_expired(secrets)
        return None
    if not token_data:
        return None

    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("psn", {})
    persisted["psn"]["access_token"] = token_data.get("access_token")
    persisted["psn"]["refresh_token"] = token_data.get("refresh_token")
    persisted["psn"]["expires_at"] = (
        datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", 3600))
    ).isoformat()
    persisted["psn"]["auth_expired"] = False
    _write_secrets(persisted)

    secrets["psn"].update({
        "access_token": persisted["psn"]["access_token"],
        "refresh_token": persisted["psn"]["refresh_token"],
        "expires_at": persisted["psn"]["expires_at"],
        "auth_expired": False,
    })
    return secrets["psn"]["access_token"]


# ---------------------------------------------------------------------------
# PSN — fetch helpers
# ---------------------------------------------------------------------------

def _fetch_psn_trophy_page(access_token: str, service: str, offset: int) -> Optional[dict]:
    """Fetch one page of trophy titles; returns parsed JSON or None on error/end."""
    try:
        resp = requests.get(
            f"{PSN_TROPHY_URL}/users/me/trophyTitles",
            params={"npServiceName": service, "limit": 800, "offset": offset},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"  PSN trophy titles fetch failed: {e}")
        return None
    if not resp.ok:
        if resp.status_code != 404:
            print(f"  PSN trophy titles ({service}): HTTP {resp.status_code}")
        return None
    return resp.json()


def fetch_psn_trophy_titles(access_token: str) -> list[dict]:
    """Return all trophy title entries for the authenticated user (PS4 + PS5)."""
    titles = []
    for service in ("trophy", "trophy2"):  # PS3/PS4 endpoint first, then PS5
        offset = 0
        while True:
            data = _fetch_psn_trophy_page(access_token, service, offset)
            if data is None:
                break
            page = data.get("trophyTitles", [])
            titles.extend(page)
            total = data.get("totalItemCount", 0)
            offset += len(page)
            if offset >= total or not page:
                break
            time.sleep(PSN_DELAY)

    return titles


# ---------------------------------------------------------------------------
# PSN — stage
# ---------------------------------------------------------------------------

def stage_psn(conn: duckdb.DuckDBPyConnection, titles: list[dict]) -> None:
    if not titles:
        return
    now = datetime.now(UTC)
    rows = []
    for t in titles:
        defined = t.get("definedTrophies", {})
        earned = t.get("earnedTrophies", {})
        total_defined = sum(defined.values()) if isinstance(defined, dict) else 0
        total_earned = sum(earned.values()) if isinstance(earned, dict) else 0
        rows.append((
            t.get("npCommunicationId", ""),
            t.get("trophyTitleName", ""),
            t.get("trophyTitleIconUrl"),
            t.get("trophyTitlePlatform", ""),
            None,  # acquisition_type not determinable from trophy titles API
            t.get("progress", 0),
            total_earned,
            total_defined,
            now,
        ))
    conn.executemany(
        """
        INSERT INTO stg_psn_library
            (np_communication_id, title, cover_url, platform, acquisition_type,
             trophy_progress, trophies_earned, trophies_defined, collected_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (np_communication_id) DO UPDATE SET
            title            = excluded.title,
            cover_url        = excluded.cover_url,
            platform         = excluded.platform,
            acquisition_type = excluded.acquisition_type,
            trophy_progress  = excluded.trophy_progress,
            trophies_earned  = excluded.trophies_earned,
            trophies_defined = excluded.trophies_defined,
            collected_at     = excluded.collected_at
        """,
        rows,
    )


# ---------------------------------------------------------------------------
# PSN — promote staging → canonical
# ---------------------------------------------------------------------------

def promote_psn(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        INSERT INTO games (title, cover_url)
        SELECT sg.title, sg.cover_url
        FROM stg_psn_library sg
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 2 AND pg.external_id = sg.np_communication_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM games g WHERE g.title = sg.title
        )
    """)

    conn.execute("""
        INSERT INTO platform_games (platform_id, external_id, game_id)
        SELECT 2, sg.np_communication_id, g.id
        FROM stg_psn_library sg
        JOIN games g ON g.title = sg.title
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 2 AND pg.external_id = sg.np_communication_id
        )
        ON CONFLICT DO NOTHING
    """)

    # PSN has no playtime; use purchase_source for acquisition_type
    conn.execute("""
        INSERT INTO library
            (platform_game_id, playtime_mins, last_played_at, never_launched,
             purchase_source, collected_at)
        SELECT pg.id, 0, NULL, FALSE, sg.acquisition_type, sg.collected_at
        FROM stg_psn_library sg
        JOIN platform_games pg
          ON pg.platform_id = 2 AND pg.external_id = sg.np_communication_id
        ON CONFLICT (platform_game_id) DO UPDATE SET
            purchase_source = excluded.purchase_source,
            collected_at    = excluded.collected_at
    """)

    # Trophy data → achievements table (same role as Steam achievement completion %)
    conn.execute("""
        INSERT INTO achievements
            (platform_game_id, unlocked_count, total_count, completion_pct, collected_at)
        SELECT pg.id, sg.trophies_earned, sg.trophies_defined,
               CAST(sg.trophy_progress AS DOUBLE), sg.collected_at
        FROM stg_psn_library sg
        JOIN platform_games pg
          ON pg.platform_id = 2 AND pg.external_id = sg.np_communication_id
        WHERE sg.trophies_defined > 0
        ON CONFLICT (platform_game_id) DO UPDATE SET
            unlocked_count = excluded.unlocked_count,
            total_count    = excluded.total_count,
            completion_pct = excluded.completion_pct,
            collected_at   = excluded.collected_at
    """)


# ---------------------------------------------------------------------------
# Nintendo Switch — token management
# ---------------------------------------------------------------------------

def _mark_switch_auth_expired(secrets: dict) -> None:
    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("switch", {})
    persisted["switch"]["auth_expired"] = True
    _write_secrets(persisted)
    secrets.setdefault("switch", {})
    secrets["switch"]["auth_expired"] = True


def _get_switch_auth(session_token: str) -> Optional[dict]:
    """
    Exchange session_token for a Nintendo Account access_token and the account's
    user ID (needed for the PCTL devices endpoint).
    Returns {"access_token": str, "user_id": str} or None.
    """
    try:
        resp = requests.post(
            f"{NINTENDO_ACCOUNTS_URL}/connect/1.0.0/api/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": _ACCEPT_JSON,
            },
            data={
                "client_id": NINTENDO_PCTL_CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer-session-token",
                "session_token": session_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except requests.RequestException as e:
        print(f"  Nintendo token exchange failed: {e}")
        return None

    access_token = token_data.get("access_token")
    if not access_token:
        print(f"  Nintendo token response missing access_token: {list(token_data.keys())}")
        return None

    try:
        user_resp = requests.get(
            NINTENDO_NA_USER_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": _ACCEPT_JSON},
            timeout=15,
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()
    except requests.RequestException as e:
        print(f"  Nintendo user info fetch failed: {e}")
        return None

    user_id = user_data.get("id")
    if not user_id:
        print(f"  Nintendo user info missing id field: {list(user_data.keys())}")
        return None

    return {"access_token": access_token, "user_id": user_id}


def _ensure_switch_auth(secrets: dict) -> Optional[dict]:
    """Return {access_token, user_id} derived from the stored session_token, or None."""
    session_token = secrets.get("switch", {}).get("session_token")
    if not session_token:
        return None
    auth = _get_switch_auth(session_token)
    if auth is None:
        _mark_switch_auth_expired(secrets)
    return auth


# ---------------------------------------------------------------------------
# Nintendo Switch — library fetch
# ---------------------------------------------------------------------------

def _pctl_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Cache-Control": "no-store",
        "Content-Type": "application/json; charset=utf-8",
        "X-Moon-App-Id": NINTENDO_PCTL_APP_ID,
        "X-Moon-Os": "ANDROID",
        "X-Moon-Os-Version": NINTENDO_PCTL_OS_VERSION,
        "X-Moon-Model": "",
        "X-Moon-TimeZone": "UTC",
        "X-Moon-Os-Language": "en-US",
        "X-Moon-App-Language": "en-US",
        "X-Moon-App-Display-Version": NINTENDO_PCTL_APP_VERSION,
        "X-Moon-App-Internal-Version": NINTENDO_PCTL_APP_BUILD,
        "User-Agent": NINTENDO_PCTL_USER_AGENT,
        "Accept": _ACCEPT_JSON,
    }


def fetch_switch_devices(access_token: str, user_id: str) -> list[str]:
    """Return device IDs linked to the Nintendo account."""
    try:
        resp = requests.get(
            f"{NINTENDO_PCTL_URL}/moon/v1/users/{user_id}/devices",
            headers=_pctl_headers(access_token),
            timeout=15,
        )
        if not resp.ok:
            if resp.status_code == 404:
                print(
                    "  PCTL devices returned 404 — no Switch registered in Parental Controls. "
                    "Open the Nintendo Switch Parental Controls app, link your console, then sync again."
                )
            else:
                print(f"  PCTL devices failed: {resp.status_code} — {resp.text[:300]}")
            return []
        data = resp.json()
        print(f"  PCTL devices raw response: {json.dumps(data)[:500]}")
        items = data if isinstance(data, list) else data.get("items", data.get("devices", []))
        return [d.get("deviceId") or d.get("id") for d in items if d.get("deviceId") or d.get("id")]
    except requests.RequestException as e:
        print(f"  PCTL devices error: {e}")
        return []


def _parse_summaries(data: dict | list, label: str) -> list[dict]:
    """Extract application play records from a PCTL summary response."""
    summaries = data if isinstance(data, list) else data.get("items", [])
    if not summaries:
        print(f"  {label}: no items in response")
        return []

    results: list[dict] = []
    for summary in summaries:
        applications = (
            summary.get("applications")
            or summary.get("monthlySummary", {}).get("applications", [])
            or summary.get("dailySummary", {}).get("applications", [])
        )
        for app in applications:
            ns_uid = app.get("applicationId") or app.get("id") or ""
            title = app.get("applicationName") or app.get("name") or ""
            play_mins = int(app.get("playingTime") or app.get("playtime") or 0)
            image_url = app.get("imageUri") or app.get("imageUrl") or app.get("image")
            if ns_uid and title:
                results.append({
                    "ns_uid": ns_uid,
                    "title": title,
                    "play_time_mins": play_mins,
                    "image_url": image_url,
                })
    return results


def _fetch_switch_summaries(access_token: str, device_id: str, by_uid: dict) -> bool:
    """Try monthly then daily summaries for one device; merge into by_uid. Returns True if data found."""
    for endpoint, label in [
        (f"{NINTENDO_PCTL_URL}/moon/v1/devices/{device_id}/monthly_summaries", "monthly_summaries"),
        (f"{NINTENDO_PCTL_URL}/moon/v1/devices/{device_id}/daily_summaries",   "daily_summaries"),
    ]:
        try:
            resp = requests.get(endpoint, headers=_pctl_headers(access_token), timeout=30)
        except requests.RequestException as e:
            print(f"  {label} request error: {e}")
            continue

        if not resp.ok:
            print(f"  {label} failed: {resp.status_code} — {resp.text[:300]}")
            continue

        data = resp.json()
        print(f"  PCTL {label} raw: {json.dumps(data)[:2000]}")

        for record in _parse_summaries(data, label):
            ns_uid = record["ns_uid"]
            if ns_uid in by_uid:
                by_uid[ns_uid]["play_time_mins"] += record["play_time_mins"]
            else:
                by_uid[ns_uid] = record

        time.sleep(NINTENDO_DELAY)

        if by_uid:
            return True  # monthly had data — skip daily

    return False


def fetch_switch_library(access_token: str, device_ids: list[str]) -> list[dict]:
    """
    Fetch play history across all linked devices, trying monthly then daily summaries.
    Returns a list of dicts with keys: ns_uid, title, play_time_mins, image_url.
    Raw API responses are logged so we can inspect the data structure.
    """
    by_uid: dict[str, dict] = {}

    for device_id in device_ids:
        print(f"  Fetching Switch library for device {device_id}...")
        _fetch_switch_summaries(access_token, device_id, by_uid)

    if not by_uid:
        print(
            "  No Switch play history found. The Switch may not have synced activity "
            "to Nintendo's servers yet — leave it connected to Wi-Fi and try again later."
        )

    return list(by_uid.values())


# ---------------------------------------------------------------------------
# Nintendo Switch — staging
# ---------------------------------------------------------------------------

def stage_switch(conn: duckdb.DuckDBPyConnection, games: list[dict]) -> None:
    if not games:
        return
    now = datetime.now(UTC)
    rows = [
        (g["ns_uid"], g["title"], g.get("image_url"), g["play_time_mins"], now)
        for g in games
    ]
    conn.executemany(
        """
        INSERT INTO stg_switch_library (ns_uid, title, image_url, play_time_mins, collected_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (ns_uid) DO UPDATE SET
            title          = excluded.title,
            image_url      = excluded.image_url,
            play_time_mins = excluded.play_time_mins,
            collected_at   = excluded.collected_at
        """,
        rows,
    )


# ---------------------------------------------------------------------------
# Nintendo Switch — promote staging → canonical
# ---------------------------------------------------------------------------

def promote_switch(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        INSERT INTO games (title, cover_url)
        SELECT sg.title, sg.image_url
        FROM stg_switch_library sg
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 4 AND pg.external_id = sg.ns_uid
        )
        AND NOT EXISTS (
            SELECT 1 FROM games g WHERE g.title = sg.title
        )
    """)

    conn.execute("""
        INSERT INTO platform_games (platform_id, external_id, game_id)
        SELECT 4, sg.ns_uid, g.id
        FROM stg_switch_library sg
        JOIN games g ON g.title = sg.title
        WHERE NOT EXISTS (
            SELECT 1 FROM platform_games pg
            WHERE pg.platform_id = 4 AND pg.external_id = sg.ns_uid
        )
        ON CONFLICT DO NOTHING
    """)

    conn.execute("""
        INSERT INTO library
            (platform_game_id, playtime_mins, last_played_at, never_launched, collected_at)
        SELECT
            pg.id,
            sg.play_time_mins,
            NULL,
            (sg.play_time_mins = 0),
            sg.collected_at
        FROM stg_switch_library sg
        JOIN platform_games pg
          ON pg.platform_id = 4 AND pg.external_id = sg.ns_uid
        ON CONFLICT (platform_game_id) DO UPDATE SET
            playtime_mins = excluded.playtime_mins,
            never_launched = excluded.never_launched,
            collected_at  = excluded.collected_at
    """)


# ---------------------------------------------------------------------------
# IGDB — token + lookup
# ---------------------------------------------------------------------------

def get_igdb_token(client_id: str, client_secret: str) -> Optional[str]:
    try:
        resp = requests.post(
            IGDB_TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except requests.RequestException as e:
        print(f"  IGDB token fetch failed: {e}")
        return None


def igdb_lookup_by_external_id(
    igdb_token: str,
    igdb_client_id: str,
    category: int,
    uid: str,
) -> Optional[int]:
    """Return the IGDB game ID for a given platform external ID, or None."""
    try:
        resp = requests.post(
            f"{IGDB_API_URL}/external_games",
            headers={
                "Authorization": f"Bearer {igdb_token}",
                "Client-ID": igdb_client_id,
            },
            data=f'fields game; where category = {category} & uid = "{uid}";',
            timeout=10,
        )
        if not resp.ok:
            return None
        results = resp.json()
        return results[0]["game"] if results else None
    except (requests.RequestException, KeyError, IndexError):
        return None


# ---------------------------------------------------------------------------
# IGDB — matching pass
# ---------------------------------------------------------------------------

def run_igdb_matching(
    conn: duckdb.DuckDBPyConnection,
    igdb_token: str,
    igdb_client_id: str,
) -> None:
    """For each platform_game whose parent games row has no igdb_id, attempt a lookup.
    When two platform_games resolve to the same IGDB id, merge their games rows."""

    rows = conn.execute("""
        SELECT pg.id AS pg_id, pg.platform_id, pg.external_id, pg.game_id
        FROM platform_games pg
        JOIN games g ON g.id = pg.game_id
        WHERE g.igdb_id IS NULL
    """).fetchall()

    print(f"  {len(rows)} platform_games need IGDB lookup")
    matched = 0

    for pg_id, platform_id, external_id, game_id in rows:
        if platform_id == PLATFORM_STEAM:
            category = IGDB_STEAM_CATEGORY
        elif platform_id == PLATFORM_PSN:
            category = IGDB_PSN_CATEGORY
        elif platform_id == PLATFORM_GOG:
            category = IGDB_GOG_CATEGORY
        else:
            continue
        igdb_game_id = igdb_lookup_by_external_id(igdb_token, igdb_client_id, category, external_id)
        time.sleep(IGDB_DELAY)

        if igdb_game_id is None:
            continue

        matched += 1

        # Check if another games row already has this igdb_id
        existing = conn.execute(
            "SELECT id FROM games WHERE igdb_id = ? AND id != ?",
            [igdb_game_id, game_id],
        ).fetchone()

        if existing:
            canonical_id = existing[0]
            # Conflict check: if the current game_id also already has an igdb_id, warn and skip
            current_igdb = conn.execute(
                "SELECT igdb_id FROM games WHERE id = ?", [game_id]
            ).fetchone()
            if current_igdb and current_igdb[0] and current_igdb[0] != igdb_game_id:
                print(
                    f"  WARN: games.id={game_id} has igdb_id={current_igdb[0]} but "
                    f"lookup returned {igdb_game_id} — skipping merge"
                )
                continue

            # Merge: point this platform_game to the canonical games row
            _merge_games_rows(conn, duplicate_id=game_id, canonical_id=canonical_id)
        else:
            # No conflict — just stamp the igdb_id on this games row
            conn.execute(
                "UPDATE games SET igdb_id = ? WHERE id = ?",
                [igdb_game_id, game_id],
            )

    print(f"  {matched} games matched to IGDB")


def _merge_games_rows(
    conn: duckdb.DuckDBPyConnection,
    duplicate_id: int,
    canonical_id: int,
) -> None:
    """Re-point all references from duplicate_id to canonical_id, then delete duplicate."""
    conn.execute(
        "UPDATE platform_games SET game_id = ? WHERE game_id = ?",
        [canonical_id, duplicate_id],
    )
    conn.execute("""
        INSERT INTO game_genres (game_id, genre_id)
        SELECT ?, genre_id FROM game_genres WHERE game_id = ?
        ON CONFLICT DO NOTHING
    """, [canonical_id, duplicate_id])
    conn.execute("DELETE FROM game_genres WHERE game_id = ?", [duplicate_id])

    conn.execute("""
        INSERT INTO game_tags (game_id, tag_id)
        SELECT ?, tag_id FROM game_tags WHERE game_id = ?
        ON CONFLICT DO NOTHING
    """, [canonical_id, duplicate_id])
    conn.execute("DELETE FROM game_tags WHERE game_id = ?", [duplicate_id])

    conn.execute("""
        INSERT INTO store_availability (game_id, platform_id, available, external_id, checked_at)
        SELECT ?, platform_id, available, external_id, checked_at
        FROM store_availability WHERE game_id = ?
        ON CONFLICT DO NOTHING
    """, [canonical_id, duplicate_id])
    conn.execute("DELETE FROM store_availability WHERE game_id = ?", [duplicate_id])

    # user_game_prefs: keep canonical's prefs if they exist, otherwise migrate
    canonical_prefs = conn.execute(
        "SELECT 1 FROM user_game_prefs WHERE game_id = ?", [canonical_id]
    ).fetchone()
    if not canonical_prefs:
        conn.execute(
            "UPDATE user_game_prefs SET game_id = ? WHERE game_id = ?",
            [canonical_id, duplicate_id],
        )
    else:
        conn.execute("DELETE FROM user_game_prefs WHERE game_id = ?", [duplicate_id])

    conn.execute("DELETE FROM games WHERE id = ?", [duplicate_id])


# ---------------------------------------------------------------------------
# Store availability pass
# ---------------------------------------------------------------------------

def run_store_availability(
    conn: duckdb.DuckDBPyConnection,
    igdb_token: str,
    igdb_client_id: str,
) -> None:
    """For each owned game with an igdb_id, check if it's available on the other platform."""
    stale_cutoff = datetime.now(UTC) - timedelta(days=7)

    # Games owned on Steam but not GOG — check GOG availability
    steam_only = conn.execute("""
        SELECT DISTINCT g.id, g.igdb_id, g.title
        FROM games g
        JOIN platform_games pg_s ON pg_s.game_id = g.id AND pg_s.platform_id = 1
        JOIN library l ON l.platform_game_id = pg_s.id
        WHERE g.igdb_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM platform_games pg_g
              WHERE pg_g.game_id = g.id AND pg_g.platform_id = 3
          )
          AND NOT EXISTS (
              SELECT 1 FROM store_availability sa
              WHERE sa.game_id = g.id AND sa.platform_id = 3
                AND sa.checked_at > ?
          )
    """, [stale_cutoff]).fetchall()

    # Games owned on GOG but not Steam — check Steam availability
    gog_only = conn.execute("""
        SELECT DISTINCT g.id, g.igdb_id, g.title
        FROM games g
        JOIN platform_games pg_g ON pg_g.game_id = g.id AND pg_g.platform_id = 3
        JOIN library l ON l.platform_game_id = pg_g.id
        WHERE g.igdb_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM platform_games pg_s
              WHERE pg_s.game_id = g.id AND pg_s.platform_id = 1
          )
          AND NOT EXISTS (
              SELECT 1 FROM store_availability sa
              WHERE sa.game_id = g.id AND sa.platform_id = 1
                AND sa.checked_at > ?
          )
    """, [stale_cutoff]).fetchall()

    # Games owned on PSN but not Steam — check Steam availability
    psn_only_check_steam = conn.execute("""
        SELECT DISTINCT g.id, g.igdb_id, g.title
        FROM games g
        JOIN platform_games pg_p ON pg_p.game_id = g.id AND pg_p.platform_id = 2
        JOIN library l ON l.platform_game_id = pg_p.id
        WHERE g.igdb_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM platform_games pg_s
              WHERE pg_s.game_id = g.id AND pg_s.platform_id = 1
          )
          AND NOT EXISTS (
              SELECT 1 FROM store_availability sa
              WHERE sa.game_id = g.id AND sa.platform_id = 1
                AND sa.checked_at > ?
          )
    """, [stale_cutoff]).fetchall()

    # Games owned on PSN but not GOG — check GOG availability
    psn_only_check_gog = conn.execute("""
        SELECT DISTINCT g.id, g.igdb_id, g.title
        FROM games g
        JOIN platform_games pg_p ON pg_p.game_id = g.id AND pg_p.platform_id = 2
        JOIN library l ON l.platform_game_id = pg_p.id
        WHERE g.igdb_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM platform_games pg_g
              WHERE pg_g.game_id = g.id AND pg_g.platform_id = 3
          )
          AND NOT EXISTS (
              SELECT 1 FROM store_availability sa
              WHERE sa.game_id = g.id AND sa.platform_id = 3
                AND sa.checked_at > ?
          )
    """, [stale_cutoff]).fetchall()

    checks = (
        [(gid, igdb_id, title, PLATFORM_GOG, IGDB_GOG_CATEGORY) for gid, igdb_id, title in steam_only] +
        [(gid, igdb_id, title, PLATFORM_STEAM, IGDB_STEAM_CATEGORY) for gid, igdb_id, title in gog_only] +
        [(gid, igdb_id, title, PLATFORM_STEAM, IGDB_STEAM_CATEGORY) for gid, igdb_id, title in psn_only_check_steam] +
        [(gid, igdb_id, title, PLATFORM_GOG, IGDB_GOG_CATEGORY) for gid, igdb_id, title in psn_only_check_gog]
    )

    print(f"  {len(checks)} store availability checks to run")
    now = datetime.now(UTC)

    for game_id, igdb_id, title, check_platform_id, igdb_category in checks:
        # Look up whether the IGDB game has an external_games entry for the target platform
        try:
            resp = requests.post(
                f"{IGDB_API_URL}/external_games",
                headers={
                    "Authorization": f"Bearer {igdb_token}",
                    "Client-ID": igdb_client_id,
                },
                data=f'fields uid; where category = {igdb_category} & game = {igdb_id};',
                timeout=10,
            )
            results = resp.json() if resp.ok else []
        except requests.RequestException:
            results = []

        time.sleep(IGDB_DELAY)

        available = bool(results)
        external_id = results[0]["uid"] if results else None

        conn.execute("""
            INSERT INTO store_availability (game_id, platform_id, available, external_id, checked_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (game_id, platform_id) DO UPDATE SET
                available   = excluded.available,
                external_id = excluded.external_id,
                checked_at  = excluded.checked_at
        """, [game_id, check_platform_id, available, external_id, now])


# ---------------------------------------------------------------------------
# Entry point — per-platform sync helpers
# ---------------------------------------------------------------------------

def _sync_steam(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:
    api_key = secrets["steam"]["api_key"]
    steam_id = secrets["steam"]["steam_id64"]
    session = make_read_session(api_key, secrets["steam"].get("session_cookie"))

    print("Fetching Steam library...")
    games = fetch_library(session, steam_id)
    print(f"  {len(games)} games found")

    print(f"Fetching app details for {len(games)} games (may take a few minutes)...")
    details: dict[int, Optional[dict]] = {}
    for i, game in enumerate(games, 1):
        details[game["appid"]] = fetch_app_details(game["appid"])
        if i % 25 == 0:
            print(f"  {i}/{len(games)}")
        time.sleep(STORE_DELAY)
    print(f"  Done — {sum(1 for d in details.values() if d)} apps returned data")

    print("Fetching achievements...")
    achievements: dict[int, tuple[int, int, float]] = {}
    for i, game in enumerate(games, 1):
        result = fetch_achievements(session, steam_id, game["appid"])
        if result:
            achievements[game["appid"]] = result
        if i % 50 == 0:
            print(f"  {i}/{len(games)}")
        time.sleep(ACH_DELAY)
    print(f"  {len(achievements)} games have achievement data")

    print("Fetching wishlist...")
    wishlist = fetch_wishlist(session, steam_id)
    print(f"  {len(wishlist)} items on wishlist")

    print("Staging Steam data...")
    stage(conn, games, details, achievements, wishlist)

    print("Promoting Steam data to canonical tables...")
    promote(conn)


def _sync_gog(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:
    gog_cfg = secrets.get("gog", {})
    if not (gog_cfg.get("access_token") and not gog_cfg.get("auth_expired")):
        print("\nGOG not connected or auth expired — skipping GOG sync")
        return

    print("\nFetching GOG library...")
    access_token = _ensure_gog_token(secrets)
    if not access_token:
        print("  GOG token unavailable after refresh attempt — skipping GOG sync")
        return

    product_ids = fetch_gog_library(access_token)
    print(f"  {len(product_ids)} GOG games found")

    print(f"Fetching GOG product details for {len(product_ids)} games...")
    products = []
    for i, pid in enumerate(product_ids, 1):
        product = fetch_gog_product(pid, access_token)
        if product:
            products.append(product)
        if i % 25 == 0:
            print(f"  {i}/{len(product_ids)}")
        time.sleep(GOG_DELAY)
    print(f"  {len(products)} products fetched")

    print("Staging GOG data...")
    stage_gog(conn, products)

    print("Promoting GOG data to canonical tables...")
    promote_gog(conn)


def _sync_psn(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:
    psn_cfg = secrets.get("psn", {})
    if not (psn_cfg.get("npsso") or psn_cfg.get("access_token")):
        print("\nPSN not connected — skipping PSN sync")
        return

    print("\nFetching PSN library...")
    access_token = _ensure_psn_token(secrets)
    if access_token:
        titles = fetch_psn_trophy_titles(access_token)
        print(f"  {len(titles)} PSN titles found")
        print("Staging PSN data...")
        stage_psn(conn, titles)
        print("Promoting PSN data to canonical tables...")
        promote_psn(conn)
    elif secrets.get("psn", {}).get("auth_expired"):
        print("  PSN session expired — reconnect via Setup page")
    else:
        print("  PSN token unavailable — skipping PSN sync")


def _sync_switch(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:
    switch_cfg = secrets.get("switch", {})
    if not (switch_cfg.get("session_token") and not switch_cfg.get("auth_expired")):
        print("\nNintendo Switch not connected — skipping Switch sync")
        return

    print("\nFetching Nintendo Switch library...")
    switch_auth = _ensure_switch_auth(secrets)
    if not switch_auth:
        if secrets.get("switch", {}).get("auth_expired"):
            print("  Nintendo Switch session expired — reconnect via Setup page")
        else:
            print("  Nintendo Switch token unavailable — skipping Switch sync")
        return

    access_token = switch_auth["access_token"]
    device_ids = fetch_switch_devices(access_token, switch_auth["user_id"])
    print(f"  {len(device_ids)} Switch device(s) found")
    if not device_ids:
        print("  No Switch devices linked to this account — skipping Switch sync")
        return

    games = fetch_switch_library(access_token, device_ids)
    print(f"  {len(games)} Switch games found")
    print("Staging Switch data...")
    stage_switch(conn, games)
    print("Promoting Switch data to canonical tables...")
    promote_switch(conn)


def _sync_igdb(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:
    igdb_cfg = secrets.get("igdb", {})
    igdb_client_id = igdb_cfg.get("client_id")
    igdb_client_secret = igdb_cfg.get("client_secret")
    if not (igdb_client_id and igdb_client_secret):
        print("\nIGDB credentials not configured — skipping matching and availability passes")
        return

    print("\nFetching IGDB token...")
    igdb_token = get_igdb_token(igdb_client_id, igdb_client_secret)
    if not igdb_token:
        print("  Could not obtain IGDB token — skipping matching and availability passes")
        return

    print("Running IGDB matching pass...")
    run_igdb_matching(conn, igdb_token, igdb_client_id)
    print("Running store availability pass...")
    run_store_availability(conn, igdb_token, igdb_client_id)


def run(platforms: set[str] = frozenset({"steam", "gog", "psn"})) -> None:
    secrets = load_secrets()
    init_db()
    conn = connect()

    if "steam" in platforms:
        _sync_steam(conn, secrets)
    else:
        print("Skipping Steam sync (not selected)")

    if "gog" in platforms:
        _sync_gog(conn, secrets)
    else:
        print("\nSkipping GOG sync (not selected)")

    if "psn" in platforms:
        _sync_psn(conn, secrets)
    else:
        print("\nSkipping PSN sync (not selected)")

    if "switch" in platforms:
        _sync_switch(conn, secrets)
    else:
        print("\nSkipping Switch sync (not selected)")

    _sync_igdb(conn, secrets)

    conn.close()
    print("\nAll done.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platforms",
        nargs="+",
        choices=["steam", "gog", "psn", "switch"],
        default=["steam", "gog", "psn", "switch"],
        help="Which platform libraries to sync (default: all)",
    )
    args = parser.parse_args()
    run(platforms=set(args.platforms))
