import json
import time
from datetime import UTC, datetime, timedelta
from typing import Optional
from urllib.parse import urlparse, parse_qs

import duckdb
import requests

from db import SECRETS_PATH
from collectors.pipeline import _write_secrets

PSN_AUTH_URL    = "https://ca.account.sony.com/api/authz/v3/oauth"
PSN_TROPHY_URL  = "https://m.np.playstation.com/api/trophy/v1"
PSN_REDIRECT_URI = "com.scee.psxandroid.scecompcall://redirect"
PSN_SCOPE       = "psn:mobile.v2.core psn:clientapp"
# Community-extracted PlayStation mobile app credentials (from psn-api source)
PSN_CLIENT_ID   = "09515159-7237-4370-9b40-3806e67c0891"
# Pre-encoded Basic Auth header value: base64(client_id:client_secret)
_PSN_BASIC_AUTH = "MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
PSN_DELAY       = 0.5


class _NpssoExpired(Exception):
    pass


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def exchange_npsso_for_tokens(npsso: str) -> Optional[dict]:
    """Exchange an NPSSO cookie for PSN OAuth tokens.
    Raises _NpssoExpired if Sony rejects the NPSSO."""
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
    """Refresh the PSN access token in-place and persist. Returns True on success."""
    psn           = secrets.get("psn", {})
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

    data        = resp.json()
    new_access  = data.get("access_token")
    new_refresh = data.get("refresh_token", refresh_token)
    expires_in  = data.get("expires_in", 3600)

    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("psn", {})
    persisted["psn"]["access_token"]  = new_access
    persisted["psn"]["refresh_token"] = new_refresh
    persisted["psn"]["expires_at"]    = (
        datetime.now(UTC) + timedelta(seconds=expires_in)
    ).isoformat()
    persisted["psn"]["auth_expired"] = False
    _write_secrets(persisted)

    secrets["psn"]["access_token"]  = new_access
    secrets["psn"]["refresh_token"] = new_refresh
    secrets["psn"]["auth_expired"]  = False
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
    # Clear a stale auth_expired flag — only re-set it if Sony explicitly rejects the NPSSO.
    if psn.get("auth_expired"):
        psn["auth_expired"] = False

    access_token = psn.get("access_token")
    if access_token:
        return _psn_token_still_valid(secrets, access_token, psn.get("expires_at", ""))

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
    persisted["psn"]["access_token"]  = token_data.get("access_token")
    persisted["psn"]["refresh_token"] = token_data.get("refresh_token")
    persisted["psn"]["expires_at"]    = (
        datetime.now(UTC) + timedelta(seconds=token_data.get("expires_in", 3600))
    ).isoformat()
    persisted["psn"]["auth_expired"] = False
    _write_secrets(persisted)

    secrets["psn"].update({
        "access_token":  persisted["psn"]["access_token"],
        "refresh_token": persisted["psn"]["refresh_token"],
        "expires_at":    persisted["psn"]["expires_at"],
        "auth_expired":  False,
    })
    return secrets["psn"]["access_token"]


# ---------------------------------------------------------------------------
# Fetch helpers
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
            page  = data.get("trophyTitles", [])
            total = data.get("totalItemCount", 0)
            titles.extend(page)
            offset += len(page)
            if offset >= total or not page:
                break
            time.sleep(PSN_DELAY)

    return titles


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------

def stage_psn(conn: duckdb.DuckDBPyConnection, titles: list[dict]) -> None:
    if not titles:
        return
    now  = datetime.now(UTC)
    rows = []
    for t in titles:
        defined      = t.get("definedTrophies", {})
        earned       = t.get("earnedTrophies", {})
        total_defined = sum(defined.values()) if isinstance(defined, dict) else 0
        total_earned  = sum(earned.values())  if isinstance(earned, dict)  else 0
        rows.append((
            t.get("npCommunicationId", ""),
            t.get("trophyTitleName", ""),
            t.get("trophyTitleIconUrl"),
            t.get("trophyTitlePlatform", ""),
            None,
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
# Promote staging → canonical
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
# Sync helper
# ---------------------------------------------------------------------------

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
