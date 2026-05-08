"""Schema correctness tests — run against a fresh in-memory DuckDB."""


def _tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    return {r[0] for r in rows}


def _columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        [table],
    ).fetchall()
    return {r[0] for r in rows}


EXPECTED_TABLES = {
    "platforms",
    "tags",
    "genres",
    "games",
    "platform_games",
    "game_tags",
    "game_genres",
    "library",
    "wishlist",
    "achievements",
    "reviews",
    "stg_steam_library",
    "stg_steam_app_details",
    "stg_steam_achievements",
    "stg_steam_wishlist",
    "stg_steam_reviews",
    "stg_gog_library",
    "stg_psn_library",
    "stg_switch_library",
    "stg_xbox_library",
    "store_availability",
    "user_game_prefs",
}


def test_all_tables_exist(db_conn):
    missing = EXPECTED_TABLES - _tables(db_conn)
    assert not missing, f"Missing tables: {missing}"


def test_platform_rows_seeded(db_conn):
    rows = db_conn.execute("SELECT id, slug FROM platforms ORDER BY id").fetchall()
    slugs = {r[1] for r in rows}
    assert len(rows) == 5
    assert slugs == {"steam", "psn", "gog", "switch", "xbox"}


def test_achievements_has_gamerscore_columns(db_conn):
    cols = _columns(db_conn, "achievements")
    assert "gamerscore_earned" in cols, "achievements.gamerscore_earned missing"
    assert "gamerscore_total" in cols, "achievements.gamerscore_total missing"


def test_library_has_purchase_source(db_conn):
    cols = _columns(db_conn, "library")
    assert "purchase_source" in cols, "library.purchase_source missing"
