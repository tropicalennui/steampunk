import json
import time
from datetime import UTC, datetime, timedelta
from typing import Optional

import duckdb
import requests

from db import SECRETS_PATH
from collectors.pipeline import _write_secrets

GOG_AUTH_URL  = "https://auth.gog.com"
GOG_EMBED_URL = "https://embed.gog.com"
GOG_API_URL   = "https://api.gog.com"
GOG_DELAY     = 0.5


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------

def refresh_gog_token(secrets: dict) -> bool:
    """Refresh the GOG access token in-place and persist. Returns True on success."""
    gog = secrets.get("gog", {})
    refresh_token = gog.get("refresh_token")
    client_id     = gog.get("client_id")
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

    data        = resp.json()
    new_access  = data.get("access_token")
    new_refresh = data.get("refresh_token", refresh_token)
    expires_in  = data.get("expires_in", 3600)

    with open(SECRETS_PATH) as f:
        persisted = json.load(f)
    persisted.setdefault("gog", {})
    persisted["gog"]["access_token"]  = new_access
    persisted["gog"]["refresh_token"] = new_refresh
    persisted["gog"]["expires_at"]    = (
        datetime.now(UTC) + timedelta(seconds=expires_in)
    ).isoformat()
    persisted["gog"]["auth_expired"] = False
    _write_secrets(persisted)

    secrets["gog"]["access_token"]  = new_access
    secrets["gog"]["refresh_token"] = new_refresh
    secrets["gog"]["auth_expired"]  = False
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
    """Return a valid GOG access token, refreshing if needed."""
    gog          = secrets.get("gog", {})
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
# Fetch helpers
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
    data   = resp.json()
    images = data.get("images", {})
    cover  = images.get("logo2x") or images.get("logo")
    if cover and cover.startswith("//"):
        cover = "https:" + cover

    release_date = None
    release_ts   = data.get("globalReleaseDate")
    if release_ts:
        try:
            release_date = datetime.fromtimestamp(release_ts, UTC).date()
        except (OSError, OverflowError):
            pass

    return {
        "product_id": str(product_id),
        "title":      data.get("title", ""),
        "cover_url":  cover,
        "release_date": release_date,
    }


# ---------------------------------------------------------------------------
# Stage
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
# Promote staging → canonical
# ---------------------------------------------------------------------------

def promote_gog(conn: duckdb.DuckDBPyConnection) -> None:
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
# Sync helper
# ---------------------------------------------------------------------------

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
