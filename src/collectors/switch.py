import json
import time
from datetime import UTC, datetime
from typing import Optional

import duckdb
import requests

from db import SECRETS_PATH
from collectors.pipeline import _write_secrets

NINTENDO_ACCOUNTS_URL    = "https://accounts.nintendo.com"
NINTENDO_NA_USER_URL     = "https://api.accounts.nintendo.com/2.0.0/users/me"
NINTENDO_PCTL_CLIENT_ID  = "54789befb391a838"  # Nintendo Parental Controls app
NINTENDO_PCTL_URL        = "https://api-lp1.pctl.srv.nintendo.net"
NINTENDO_PCTL_APP_ID     = "com.nintendo.znma"
NINTENDO_PCTL_APP_VERSION = "2.4.0"
NINTENDO_PCTL_APP_BUILD  = "660"
NINTENDO_PCTL_OS_VERSION = "26"
NINTENDO_PCTL_USER_AGENT = (
    f"moon_ANDROID/{NINTENDO_PCTL_APP_VERSION} "
    f"(com.nintendo.znma; build:{NINTENDO_PCTL_APP_BUILD}; ANDROID {NINTENDO_PCTL_OS_VERSION})"
)
NINTENDO_DELAY = 0.5
_ACCEPT_JSON   = "application/json"


# ---------------------------------------------------------------------------
# Auth helpers
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
    """Exchange session_token for a Nintendo Account access_token and user_id."""
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
    """Return {access_token, user_id} from the stored session_token, or None."""
    session_token = secrets.get("switch", {}).get("session_token")
    if not session_token:
        return None
    auth = _get_switch_auth(session_token)
    if auth is None:
        _mark_switch_auth_expired(secrets)
    return auth


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _pctl_headers(access_token: str) -> dict:
    return {
        "Authorization":              f"Bearer {access_token}",
        "Cache-Control":              "no-store",
        "Content-Type":               "application/json; charset=utf-8",
        "X-Moon-App-Id":              NINTENDO_PCTL_APP_ID,
        "X-Moon-Os":                  "ANDROID",
        "X-Moon-Os-Version":          NINTENDO_PCTL_OS_VERSION,
        "X-Moon-Model":               "",
        "X-Moon-TimeZone":            "UTC",
        "X-Moon-Os-Language":         "en-US",
        "X-Moon-App-Language":        "en-US",
        "X-Moon-App-Display-Version": NINTENDO_PCTL_APP_VERSION,
        "X-Moon-App-Internal-Version": NINTENDO_PCTL_APP_BUILD,
        "User-Agent":                 NINTENDO_PCTL_USER_AGENT,
        "Accept":                     _ACCEPT_JSON,
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
        data  = resp.json()
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
            ns_uid    = app.get("applicationId") or app.get("id") or ""
            title     = app.get("applicationName") or app.get("name") or ""
            play_mins = int(app.get("playingTime") or app.get("playtime") or 0)
            image_url = app.get("imageUri") or app.get("imageUrl") or app.get("image")
            if ns_uid and title:
                results.append({
                    "ns_uid":        ns_uid,
                    "title":         title,
                    "play_time_mins": play_mins,
                    "image_url":     image_url,
                })
    return results


def _fetch_switch_summaries(access_token: str, device_id: str, by_uid: dict) -> bool:
    """Try monthly then daily summaries for one device; merge into by_uid."""
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
    """Fetch play history across all linked devices."""
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
# Stage
# ---------------------------------------------------------------------------

def stage_switch(conn: duckdb.DuckDBPyConnection, games: list[dict]) -> None:
    if not games:
        return
    now  = datetime.now(UTC)
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
# Promote staging → canonical
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
            playtime_mins  = excluded.playtime_mins,
            never_launched = excluded.never_launched,
            collected_at   = excluded.collected_at
    """)


# ---------------------------------------------------------------------------
# Sync helper
# ---------------------------------------------------------------------------

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
    device_ids   = fetch_switch_devices(access_token, switch_auth["user_id"])
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
