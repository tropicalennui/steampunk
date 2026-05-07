"""Tests for collectors/igdb.py functions beyond the basic lookup (already in test_igdb.py)."""
from unittest.mock import MagicMock, patch

import pytest

from collectors.igdb import get_igdb_token, run_igdb_matching, run_store_availability
from collectors.pipeline import _merge_games_rows


def _mock_resp(ok: bool, json_data=None) -> MagicMock:
    r = MagicMock()
    r.ok = ok
    if json_data is not None:
        r.json.return_value = json_data
    return r


# ── get_igdb_token ─────────────────────────────────────────────────────────────

def test_get_igdb_token_returns_token_on_success():
    mock_resp = _mock_resp(True, {"access_token": "igdb-tok"})
    mock_resp.raise_for_status = MagicMock()
    with patch("collectors.igdb.requests.post", return_value=mock_resp):
        result = get_igdb_token("client-id", "client-secret")
    assert result == "igdb-tok"


def test_get_igdb_token_returns_none_on_exception():
    import requests as _r
    with patch("collectors.igdb.requests.post", side_effect=_r.RequestException("timeout")):
        result = get_igdb_token("client-id", "client-secret")
    assert result is None


# ── _merge_games_rows ─────────────────────────────────────────────────────────

def test_merge_games_rows_repoints_and_deletes_duplicate(db_conn):
    # No library rows — DuckDB FK revalidation on platform_games UPDATE
    # raises if library references the same platform_games rows.
    db_conn.execute("INSERT INTO games (title) VALUES ('Dupe'), ('Canon')")
    rows = db_conn.execute("SELECT id FROM games ORDER BY id").fetchall()
    dupe_id, canon_id = rows[0][0], rows[1][0]

    db_conn.execute(
        "INSERT INTO platform_games (platform_id, external_id, game_id) VALUES (1, 'ext1', ?)",
        [dupe_id],
    )
    _merge_games_rows(db_conn, duplicate_id=dupe_id, canonical_id=canon_id)

    games_left = db_conn.execute("SELECT id FROM games").fetchall()
    assert all(g[0] != dupe_id for g in games_left)

    pg_game_ids = [r[0] for r in db_conn.execute("SELECT game_id FROM platform_games").fetchall()]
    assert all(gid == canon_id for gid in pg_game_ids)


# ── run_igdb_matching ─────────────────────────────────────────────────────────

def _setup_steam_game(db_conn, title="Dota 2", app_id="570"):
    db_conn.execute(f"INSERT INTO games (title) VALUES ('{title}')")
    game_id = db_conn.execute("SELECT id FROM games WHERE title = ?", [title]).fetchone()[0]
    db_conn.execute(
        "INSERT INTO platform_games (platform_id, external_id, game_id) VALUES (1, ?, ?)",
        [app_id, game_id],
    )
    db_conn.execute(
        "INSERT INTO library (platform_game_id, playtime_mins, never_launched, collected_at) "
        "SELECT id, 0, FALSE, NOW() FROM platform_games WHERE external_id = ?",
        [app_id],
    )
    return game_id


def test_run_igdb_matching_sets_igdb_id(db_conn):
    game_id = _setup_steam_game(db_conn)
    with patch("collectors.igdb.igdb_lookup_by_external_id", return_value=9999), \
         patch("collectors.igdb.time.sleep"):
        run_igdb_matching(db_conn, "tok", "cid")
    igdb_id = db_conn.execute("SELECT igdb_id FROM games WHERE id = ?", [game_id]).fetchone()[0]
    assert igdb_id == 9999


def test_run_igdb_matching_merges_when_igdb_id_already_exists(db_conn):
    # No library row — DuckDB revalidates all FKs on platform_games update,
    # which fails if library has a referencing row.
    db_conn.execute("INSERT INTO games (title) VALUES ('Dota 2')")
    game_id1 = db_conn.execute("SELECT id FROM games WHERE title = 'Dota 2'").fetchone()[0]
    db_conn.execute(
        "INSERT INTO platform_games (platform_id, external_id, game_id) VALUES (1, '570', ?)",
        [game_id1],
    )
    db_conn.execute("INSERT INTO games (title, igdb_id) VALUES ('Dota 2 Canon', 9999)")
    canon_id = db_conn.execute("SELECT id FROM games WHERE igdb_id = 9999").fetchone()[0]

    with patch("collectors.igdb.igdb_lookup_by_external_id", return_value=9999), \
         patch("collectors.igdb.time.sleep"):
        run_igdb_matching(db_conn, "tok", "cid")

    remaining_ids = [r[0] for r in db_conn.execute("SELECT id FROM games").fetchall()]
    assert game_id1 not in remaining_ids
    assert canon_id in remaining_ids


def test_run_igdb_matching_skips_unknown_platforms(db_conn):
    db_conn.execute("INSERT INTO games (title) VALUES ('Switch Game')")
    game_id = db_conn.execute("SELECT id FROM games WHERE title = 'Switch Game'").fetchone()[0]
    db_conn.execute(
        "INSERT INTO platform_games (platform_id, external_id, game_id) VALUES (4, 'ns-uid', ?)",
        [game_id],
    )
    with patch("collectors.igdb.igdb_lookup_by_external_id", return_value=1234) as mock_lookup, \
         patch("collectors.igdb.time.sleep"):
        run_igdb_matching(db_conn, "tok", "cid")
    mock_lookup.assert_not_called()


def test_run_igdb_matching_skips_when_no_match(db_conn):
    _setup_steam_game(db_conn)
    with patch("collectors.igdb.igdb_lookup_by_external_id", return_value=None), \
         patch("collectors.igdb.time.sleep"):
        run_igdb_matching(db_conn, "tok", "cid")
    igdb_ids = [r[0] for r in db_conn.execute("SELECT igdb_id FROM games").fetchall()]
    assert all(i is None for i in igdb_ids)


# ── run_store_availability ────────────────────────────────────────────────────

def _setup_steam_game_with_igdb(db_conn, title="Dota 2", app_id="570", igdb_id=9999):
    db_conn.execute(f"INSERT INTO games (title, igdb_id) VALUES ('{title}', {igdb_id})")
    game_id = db_conn.execute("SELECT id FROM games WHERE title = ?", [title]).fetchone()[0]
    db_conn.execute(
        "INSERT INTO platform_games (platform_id, external_id, game_id) VALUES (1, ?, ?)",
        [app_id, game_id],
    )
    db_conn.execute(
        "INSERT INTO library (platform_game_id, playtime_mins, never_launched, collected_at) "
        "SELECT id, 0, FALSE, NOW() FROM platform_games WHERE external_id = ?",
        [app_id],
    )
    return game_id


def test_run_store_availability_inserts_availability_record(db_conn):
    _setup_steam_game_with_igdb(db_conn)
    gog_result = [{"uid": "1234567890"}]
    with patch("collectors.igdb.requests.post", return_value=_mock_resp(True, gog_result)), \
         patch("collectors.igdb.time.sleep"):
        run_store_availability(db_conn, "tok", "cid")
    rows = db_conn.execute("SELECT available, external_id FROM store_availability").fetchall()
    assert len(rows) == 1
    assert rows[0][0] is True
    assert rows[0][1] == "1234567890"


def test_run_store_availability_marks_unavailable_when_no_results(db_conn):
    _setup_steam_game_with_igdb(db_conn)
    with patch("collectors.igdb.requests.post", return_value=_mock_resp(True, [])), \
         patch("collectors.igdb.time.sleep"):
        run_store_availability(db_conn, "tok", "cid")
    rows = db_conn.execute("SELECT available FROM store_availability").fetchall()
    assert rows[0][0] is False


def test_run_store_availability_handles_request_exception(db_conn):
    import requests as _r
    _setup_steam_game_with_igdb(db_conn)
    with patch("collectors.igdb.requests.post", side_effect=_r.RequestException("timeout")), \
         patch("collectors.igdb.time.sleep"):
        run_store_availability(db_conn, "tok", "cid")
    rows = db_conn.execute("SELECT available FROM store_availability").fetchall()
    assert rows[0][0] is False
