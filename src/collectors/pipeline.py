import json

from db import SECRETS_PATH

PLATFORM_STEAM  = 1
PLATFORM_PSN    = 2
PLATFORM_GOG    = 3
PLATFORM_SWITCH = 4
PLATFORM_XBOX   = 5

IGDB_STEAM_CATEGORY = 1
IGDB_GOG_CATEGORY   = 5
IGDB_PSN_CATEGORY   = 36  # PlayStation Store US


def _write_secrets(data: dict) -> None:
    with open(SECRETS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _merge_games_rows(conn, duplicate_id: int, canonical_id: int) -> None:
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
