"""Stage + promote pipeline tests — all platforms, including idempotency."""
from datetime import UTC, datetime

import pytest

from collect import (
    promote,
    promote_gog,
    promote_psn,
    promote_switch,
    promote_xbox,
    stage,
    stage_gog,
    stage_psn,
    stage_switch,
    stage_xbox,
)
from conftest import MockAchievement, MockTitleHistory, MockXboxTitle


# ── helpers ───────────────────────────────────────────────────────────────────

def _count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _rows(conn, table: str) -> list[dict]:
    result = conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in result.description]
    return [dict(zip(cols, r)) for r in result.fetchall()]


# ── Xbox ──────────────────────────────────────────────────────────────────────

_XBOX_TITLE_WITH_ACH = MockXboxTitle(
    title_id=11111,
    name="Halo Infinite",
    achievement=MockAchievement(
        current_achievements=10,
        total_achievements=50,
        current_gamerscore=200,
        total_gamerscore=1000,
    ),
    title_history=MockTitleHistory(last_time_played=datetime(2024, 3, 1, tzinfo=UTC)),
)

_XBOX_TITLE_ZERO_ACH = MockXboxTitle(
    title_id=22222,
    name="No-Achievement Game",
    achievement=MockAchievement(
        current_achievements=0,
        total_achievements=0,
        current_gamerscore=0,
        total_gamerscore=0,
    ),
    title_history=None,
)

_XBOX_TITLES = [_XBOX_TITLE_WITH_ACH, _XBOX_TITLE_ZERO_ACH]


def test_stage_xbox_inserts_rows(db_conn):
    stage_xbox(db_conn, _XBOX_TITLES)
    rows = _rows(db_conn, "stg_xbox_library")
    assert len(rows) == 2
    by_id = {r["title_id"]: r for r in rows}
    assert by_id["11111"]["title"] == "Halo Infinite"
    assert by_id["11111"]["gamerscore_earned"] == 200
    assert by_id["11111"]["gamerscore_total"] == 1000
    assert by_id["22222"]["achievements_total"] == 0


def test_promote_xbox_creates_canonical_rows(db_conn):
    stage_xbox(db_conn, _XBOX_TITLES)
    promote_xbox(db_conn)

    assert _count(db_conn, "games") == 2
    assert _count(db_conn, "platform_games") == 2
    assert _count(db_conn, "library") == 2


def test_promote_xbox_skips_zero_achievement_rows(db_conn):
    stage_xbox(db_conn, _XBOX_TITLES)
    promote_xbox(db_conn)
    # Only the title with achievements_total > 0 gets an achievements row
    assert _count(db_conn, "achievements") == 1
    row = _rows(db_conn, "achievements")[0]
    assert row["unlocked_count"] == 10
    assert row["total_count"] == 50
    assert row["gamerscore_earned"] == 200
    assert row["gamerscore_total"] == 1000


def test_promote_xbox_sets_purchase_source_unknown(db_conn):
    stage_xbox(db_conn, _XBOX_TITLES)
    promote_xbox(db_conn)
    lib_rows = _rows(db_conn, "library")
    assert all(r["purchase_source"] == "unknown" for r in lib_rows)


def test_stage_xbox_idempotent(db_conn):
    stage_xbox(db_conn, _XBOX_TITLES)
    stage_xbox(db_conn, _XBOX_TITLES)
    assert _count(db_conn, "stg_xbox_library") == 2


def test_promote_xbox_idempotent(db_conn):
    stage_xbox(db_conn, _XBOX_TITLES)
    promote_xbox(db_conn)
    promote_xbox(db_conn)
    assert _count(db_conn, "games") == 2
    assert _count(db_conn, "library") == 2
    assert _count(db_conn, "achievements") == 1


# ── Steam ─────────────────────────────────────────────────────────────────────

_STEAM_GAMES = [
    {
        "appid": 570,
        "name": "Dota 2",
        "playtime_forever": 120,
        "playtime_2weeks": 30,
        "rtime_last_played": 1700000000,
    }
]
_STEAM_DETAILS = {
    570: {
        "name": "Dota 2",
        "genres": [{"description": "Strategy"}],
        "categories": [],
        "content_descriptors": {"ids": []},
        "header_image": "https://example.com/dota2.jpg",
        "release_date": {"date": "2013-07-09"},
    }
}
_STEAM_ACHIEVEMENTS = {570: (100, 200, 50.0)}
_STEAM_WISHLIST: list = []


def test_stage_steam_inserts_rows(db_conn):
    stage(db_conn, _STEAM_GAMES, _STEAM_DETAILS, _STEAM_ACHIEVEMENTS, _STEAM_WISHLIST)
    assert _count(db_conn, "stg_steam_library") == 1
    assert _count(db_conn, "stg_steam_app_details") == 1
    assert _count(db_conn, "stg_steam_achievements") == 1


def test_promote_steam_creates_canonical_rows(db_conn):
    stage(db_conn, _STEAM_GAMES, _STEAM_DETAILS, _STEAM_ACHIEVEMENTS, _STEAM_WISHLIST)
    promote(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "platform_games") == 1
    assert _count(db_conn, "library") == 1
    assert _count(db_conn, "achievements") == 1


def test_promote_steam_idempotent(db_conn):
    stage(db_conn, _STEAM_GAMES, _STEAM_DETAILS, _STEAM_ACHIEVEMENTS, _STEAM_WISHLIST)
    promote(db_conn)
    stage(db_conn, _STEAM_GAMES, _STEAM_DETAILS, _STEAM_ACHIEVEMENTS, _STEAM_WISHLIST)
    promote(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "library") == 1
    assert _count(db_conn, "achievements") == 1


# ── GOG ───────────────────────────────────────────────────────────────────────

_GOG_PRODUCTS = [
    {
        "product_id": "1234567890",
        "title": "The Witcher 3",
        "cover_url": "https://example.com/witcher3.jpg",
        "release_date": None,
    }
]


def test_stage_gog_inserts_rows(db_conn):
    stage_gog(db_conn, _GOG_PRODUCTS)
    assert _count(db_conn, "stg_gog_library") == 1


def test_promote_gog_creates_canonical_rows(db_conn):
    stage_gog(db_conn, _GOG_PRODUCTS)
    promote_gog(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "platform_games") == 1
    assert _count(db_conn, "library") == 1


def test_promote_gog_idempotent(db_conn):
    stage_gog(db_conn, _GOG_PRODUCTS)
    promote_gog(db_conn)
    stage_gog(db_conn, _GOG_PRODUCTS)
    promote_gog(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "library") == 1


# ── PSN ───────────────────────────────────────────────────────────────────────

_PSN_TITLES = [
    {
        "npCommunicationId": "NPWR12345_00",
        "trophyTitleName": "Ghost of Tsushima",
        "trophyTitleIconUrl": "https://example.com/got.jpg",
        "trophyTitlePlatform": "PS4",
        "progress": 65,
        "definedTrophies": {"bronze": 20, "silver": 10, "gold": 5, "platinum": 1},
        "earnedTrophies": {"bronze": 15, "silver": 6, "gold": 2, "platinum": 0},
    }
]


def test_stage_psn_inserts_rows(db_conn):
    stage_psn(db_conn, _PSN_TITLES)
    assert _count(db_conn, "stg_psn_library") == 1
    row = _rows(db_conn, "stg_psn_library")[0]
    assert row["np_communication_id"] == "NPWR12345_00"
    assert row["trophies_defined"] == 36  # 20+10+5+1


def test_promote_psn_creates_canonical_rows(db_conn):
    stage_psn(db_conn, _PSN_TITLES)
    promote_psn(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "platform_games") == 1
    assert _count(db_conn, "library") == 1
    assert _count(db_conn, "achievements") == 1


def test_promote_psn_idempotent(db_conn):
    stage_psn(db_conn, _PSN_TITLES)
    promote_psn(db_conn)
    stage_psn(db_conn, _PSN_TITLES)
    promote_psn(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "library") == 1
    assert _count(db_conn, "achievements") == 1


# ── Nintendo Switch ───────────────────────────────────────────────────────────

_SWITCH_GAMES = [
    {
        "ns_uid": "0100F2C0115B6000",
        "title": "The Legend of Zelda: Tears of the Kingdom",
        "image_url": "https://example.com/totk.jpg",
        "play_time_mins": 480,
    }
]


def test_stage_switch_inserts_rows(db_conn):
    stage_switch(db_conn, _SWITCH_GAMES)
    assert _count(db_conn, "stg_switch_library") == 1
    row = _rows(db_conn, "stg_switch_library")[0]
    assert row["ns_uid"] == "0100F2C0115B6000"
    assert row["play_time_mins"] == 480


def test_promote_switch_creates_canonical_rows(db_conn):
    stage_switch(db_conn, _SWITCH_GAMES)
    promote_switch(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "platform_games") == 1
    assert _count(db_conn, "library") == 1


def test_promote_switch_idempotent(db_conn):
    stage_switch(db_conn, _SWITCH_GAMES)
    promote_switch(db_conn)
    stage_switch(db_conn, _SWITCH_GAMES)
    promote_switch(db_conn)
    assert _count(db_conn, "games") == 1
    assert _count(db_conn, "library") == 1
