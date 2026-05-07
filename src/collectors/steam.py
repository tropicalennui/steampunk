import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Optional

import duckdb
import requests

STEAM_API   = "https://api.steampowered.com"
STORE_API   = "https://store.steampowered.com/api"
WISHLIST_URL = "https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/"

STORE_DELAY = 0.5
ACH_DELAY   = 0.3

_STEAM_DOMAINS = [
    "api.steampowered.com",
    "store.steampowered.com",
    "steamcommunity.com",
]


# ---------------------------------------------------------------------------
# Session factory
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
# Fetch helpers
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
        name   = game.findtext("name")
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


def fetch_achievements(
    session: requests.Session, steam_id: str, app_id: int
) -> Optional[tuple[int, int, float]]:
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
        total    = len(achievements)
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
# Stage
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
# Promote staging → canonical
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
# Sync helper
# ---------------------------------------------------------------------------

def _sync_steam(conn: duckdb.DuckDBPyConnection, secrets: dict) -> None:
    api_key  = secrets["steam"]["api_key"]
    steam_id = secrets["steam"]["steam_id64"]
    session  = make_read_session(api_key, secrets["steam"].get("session_cookie"))

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
