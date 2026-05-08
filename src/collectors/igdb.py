import time
from datetime import UTC, datetime, timedelta
from typing import Optional

import duckdb
import requests

from collectors.pipeline import (
    PLATFORM_STEAM, PLATFORM_PSN, PLATFORM_GOG,
    IGDB_STEAM_CATEGORY, IGDB_GOG_CATEGORY, IGDB_PSN_CATEGORY,
    _merge_games_rows,
)

IGDB_API_URL   = "https://api.igdb.com/v4"
IGDB_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_DELAY     = 0.25


# ---------------------------------------------------------------------------
# Token + lookup
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
    _debug: bool = False,
) -> Optional[int]:
    """Return the IGDB game ID for a given platform external ID, or None."""
    try:
        resp = requests.post(
            f"{IGDB_API_URL}/external_games",
            headers={
                "Authorization": f"Bearer {igdb_token}",
                "Client-ID": igdb_client_id,
            },
            data=f'fields game; where external_game_source = {category} & uid = "{uid}";',
            timeout=10,
        )
        if not resp.ok:
            if _debug:
                print(f"    IGDB {resp.status_code} for category={category} uid={uid!r}: {resp.text[:200]}")
            return None
        results = resp.json()
        return results[0]["game"] if results else None
    except (requests.RequestException, KeyError, IndexError):
        return None


def igdb_lookup_by_name(
    igdb_token: str,
    igdb_client_id: str,
    title: str,
) -> Optional[int]:
    """Return the IGDB game ID for an exact title match, or None."""
    escaped = title.replace('"', '\\"')
    try:
        resp = requests.post(
            f"{IGDB_API_URL}/games",
            headers={
                "Authorization": f"Bearer {igdb_token}",
                "Client-ID": igdb_client_id,
            },
            data=f'fields id; where name = "{escaped}" & version_parent = null; limit 1;',
            timeout=10,
        )
        if not resp.ok:
            return None
        results = resp.json()
        return results[0]["id"] if results else None
    except (requests.RequestException, KeyError, IndexError):
        return None


# ---------------------------------------------------------------------------
# IGDB matching pass
# ---------------------------------------------------------------------------

_PLATFORM_SOURCE: dict[int, int] = {
    PLATFORM_STEAM: IGDB_STEAM_CATEGORY,
    PLATFORM_PSN:   IGDB_PSN_CATEGORY,
    PLATFORM_GOG:   IGDB_GOG_CATEGORY,
}


def _resolve_igdb_id(
    igdb_token: str,
    igdb_client_id: str,
    platform_id: int,
    external_id: str,
    title: str,
) -> Optional[int]:
    """Try external-ID lookup first, fall back to exact name match."""
    source = _PLATFORM_SOURCE.get(platform_id)
    if source is None:
        return None
    igdb_id = igdb_lookup_by_external_id(igdb_token, igdb_client_id, source, external_id)
    time.sleep(IGDB_DELAY)
    if igdb_id is None:
        igdb_id = igdb_lookup_by_name(igdb_token, igdb_client_id, title)
        time.sleep(IGDB_DELAY)
    return igdb_id


def _apply_igdb_match(
    conn: duckdb.DuckDBPyConnection,
    game_id: int,
    igdb_game_id: int,
) -> None:
    """Set igdb_id on the game row, merging into an existing canonical row if needed."""
    existing = conn.execute(
        "SELECT id FROM games WHERE igdb_id = ? AND id != ?",
        [igdb_game_id, game_id],
    ).fetchone()
    if existing:
        canonical_id = existing[0]
        current_igdb = conn.execute(
            "SELECT igdb_id FROM games WHERE id = ?", [game_id]
        ).fetchone()
        if current_igdb and current_igdb[0] and current_igdb[0] != igdb_game_id:
            print(
                f"  WARN: games.id={game_id} has igdb_id={current_igdb[0]} but "
                f"lookup returned {igdb_game_id} — skipping merge"
            )
            return
        _merge_games_rows(conn, duplicate_id=game_id, canonical_id=canonical_id)
    else:
        conn.execute("UPDATE games SET igdb_id = ? WHERE id = ?", [igdb_game_id, game_id])


def run_igdb_matching(
    conn: duckdb.DuckDBPyConnection,
    igdb_token: str,
    igdb_client_id: str,
) -> None:
    """For each platform_game whose parent games row has no igdb_id, attempt a lookup."""
    rows = conn.execute("""
        SELECT pg.id AS pg_id, pg.platform_id, pg.external_id, pg.game_id, g.title
        FROM platform_games pg
        JOIN games g ON g.id = pg.game_id
        WHERE g.igdb_id IS NULL
    """).fetchall()

    print(f"  {len(rows)} platform_games need IGDB lookup")
    matched = 0
    not_found = 0

    for _pg_id, platform_id, external_id, game_id, title in rows:
        igdb_game_id = _resolve_igdb_id(igdb_token, igdb_client_id, platform_id, external_id, title)
        if igdb_game_id is None:
            not_found += 1
            continue
        matched += 1
        _apply_igdb_match(conn, game_id, igdb_game_id)

    print(f"  {matched} games matched to IGDB ({not_found} not found in IGDB)")


# ---------------------------------------------------------------------------
# Store availability pass
# ---------------------------------------------------------------------------

def run_store_availability(
    conn: duckdb.DuckDBPyConnection,
    igdb_token: str,
    igdb_client_id: str,
) -> None:
    """For each owned game with an igdb_id, check availability on the other platform."""
    stale_cutoff = datetime.now(UTC) - timedelta(days=7)

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
        [(gid, igdb_id, title, PLATFORM_GOG,   IGDB_GOG_CATEGORY)   for gid, igdb_id, title in steam_only] +
        [(gid, igdb_id, title, PLATFORM_STEAM,  IGDB_STEAM_CATEGORY) for gid, igdb_id, title in gog_only] +
        [(gid, igdb_id, title, PLATFORM_STEAM,  IGDB_STEAM_CATEGORY) for gid, igdb_id, title in psn_only_check_steam] +
        [(gid, igdb_id, title, PLATFORM_GOG,    IGDB_GOG_CATEGORY)   for gid, igdb_id, title in psn_only_check_gog]
    )

    print(f"  {len(checks)} store availability checks to run")
    now = datetime.now(UTC)

    for game_id, igdb_id, title, check_platform_id, igdb_category in checks:
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

        available   = bool(results)
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
# Sync helper
# ---------------------------------------------------------------------------

def _sync_igdb(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:  # pragma: no cover
    igdb_cfg          = secrets.get("igdb", {})
    igdb_client_id    = igdb_cfg.get("client_id")
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
