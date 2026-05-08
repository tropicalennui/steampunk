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
    # DuckDB treats UPDATE as DELETE+INSERT for FK checking, so tables that reference
    # platform_games.id (library, wishlist, achievements, reviews) must be temporarily
    # removed before we can update platform_games.game_id, then restored afterwards.
    pg_ids = [
        r[0] for r in conn.execute(
            "SELECT id FROM platform_games WHERE game_id = ?", [duplicate_id]
        ).fetchall()
    ]

    _REF_TABLES = ["library", "wishlist", "achievements", "reviews"]
    saved: dict[str, list] = {}
    if pg_ids:
        placeholders = ", ".join(["?"] * len(pg_ids))
        for tbl in _REF_TABLES:
            rows = conn.execute(
                f"SELECT * FROM {tbl} WHERE platform_game_id IN ({placeholders})", pg_ids
            ).fetchall()
            if rows:
                conn.execute(
                    f"DELETE FROM {tbl} WHERE platform_game_id IN ({placeholders})", pg_ids
                )
            saved[tbl] = rows

    conn.execute(
        "UPDATE platform_games SET game_id = ? WHERE game_id = ?",
        [canonical_id, duplicate_id],
    )

    for tbl in _REF_TABLES:
        for row in saved.get(tbl, []):
            n = len(row)
            conn.execute(
                f"INSERT INTO {tbl} VALUES ({', '.join(['?'] * n)}) ON CONFLICT DO NOTHING",
                list(row),
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

    dup_prefs = conn.execute(
        "SELECT rating, hidden, updated_at FROM user_game_prefs WHERE game_id = ?", [duplicate_id]
    ).fetchone()
    if dup_prefs:
        conn.execute("DELETE FROM user_game_prefs WHERE game_id = ?", [duplicate_id])
        canonical_prefs = conn.execute(
            "SELECT 1 FROM user_game_prefs WHERE game_id = ?", [canonical_id]
        ).fetchone()
        if not canonical_prefs:
            conn.execute(
                "INSERT INTO user_game_prefs (game_id, rating, hidden, updated_at) VALUES (?, ?, ?, ?)",
                [canonical_id, dup_prefs[0], dup_prefs[1], dup_prefs[2]],
            )

    conn.execute("DELETE FROM games WHERE id = ?", [duplicate_id])
