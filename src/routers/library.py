"""Library, profile, list-view API, and merge/rating endpoints."""
import sys
from dataclasses import dataclass, field
from typing import Optional, Union

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from shared import get_db, _query, _last_synced, templates, _URL_LIBRARY

import logging
logger = logging.getLogger(__name__)

router = APIRouter()


def _user(request: Request):
    """Reads _user from main at call time so monkeypatch.setattr(main, '_user', ...) works."""
    return sys.modules["main"]._user(request)


# ---------------------------------------------------------------------------
# Column registry for list-view API
# ---------------------------------------------------------------------------

_GRP_LIB  = "Library data"
_GRP_PLAT = "Platform data"


@dataclass
class ColumnDef:
    label:      str
    group:      str
    platforms:  frozenset
    select_sql: Union[str, dict]
    join_sql:   Union[str, dict, None] = None
    default:    bool = False


_J_STEAM_LIB = "LEFT JOIN stg_steam_library ssl ON ssl.app_id = TRY_CAST(pg.external_id AS INTEGER)"
_J_STEAM_DET = "LEFT JOIN stg_steam_app_details sad ON sad.app_id = TRY_CAST(pg.external_id AS INTEGER)"
_J_GOG       = "LEFT JOIN stg_gog_library sgog ON sgog.product_id = pg.external_id"
_J_PSN       = "LEFT JOIN stg_psn_library spsn ON spsn.np_communication_id = pg.external_id"
_J_ACH       = "LEFT JOIN achievements ach ON ach.platform_game_id = pg.id"
_J_REV       = "LEFT JOIN reviews rv ON rv.platform_game_id = pg.id"
_J_GENRES    = "LEFT JOIN game_genres gg ON gg.game_id = g.id LEFT JOIN genres gn ON gn.id = gg.genre_id"
_J_TAGS      = "LEFT JOIN game_tags gt ON gt.game_id = g.id LEFT JOIN tags tg ON tg.id = gt.tag_id"

COLUMN_REGISTRY: dict[str, ColumnDef] = {
    # ── Library data (canonical) ──────────────────────────────────────────────
    "playtime_mins": ColumnDef(
        label="Playtime (total)", group=_GRP_LIB,
        platforms=frozenset({"steam", "switch"}),
        select_sql="MAX(l.playtime_mins) AS playtime_mins",
        default=True,
    ),
    "last_played_at": ColumnDef(
        label="Last played", group=_GRP_LIB,
        platforms=frozenset({"steam"}),
        select_sql="MAX(l.last_played_at) AS last_played_at",
        default=True,
    ),
    "first_played_at": ColumnDef(
        label="First played", group=_GRP_LIB,
        platforms=frozenset({"steam"}),
        select_sql="MAX(l.first_played_at) AS first_played_at",
    ),
    "never_launched": ColumnDef(
        label="Never launched", group=_GRP_LIB,
        platforms=frozenset({"steam"}),
        select_sql="bool_and(l.never_launched) AS never_launched",
    ),
    "purchased_at": ColumnDef(
        label="Purchased at", group=_GRP_LIB,
        platforms=frozenset({"steam", "gog", "psn", "switch"}),
        select_sql="MAX(l.purchased_at) AS purchased_at",
    ),
    "purchase_source": ColumnDef(
        label="Purchase source", group=_GRP_LIB,
        platforms=frozenset({"steam", "gog", "psn", "switch"}),
        select_sql="MAX(l.purchase_source) AS purchase_source",
    ),
    # ── Platform data: Steam ──────────────────────────────────────────────────
    "playtime_2weeks": ColumnDef(
        label="Playtime (last 2 weeks)", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="any_value(ssl.playtime_2weeks_mins) AS playtime_2weeks",
        join_sql=_J_STEAM_LIB,
    ),
    "release_date": ColumnDef(
        label="Release date", group=_GRP_PLAT,
        platforms=frozenset({"steam", "gog"}),
        select_sql={
            "steam": "any_value(sad.release_date) AS release_date",
            "gog":   "CAST(any_value(sgog.release_date) AS VARCHAR) AS release_date",
        },
        join_sql={"steam": _J_STEAM_DET, "gog": _J_GOG},
    ),
    "genres": ColumnDef(
        label="Genres", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="list_distinct(list(gn.name)) FILTER (WHERE gn.name IS NOT NULL) AS genres",
        join_sql=_J_GENRES,
        default=True,
    ),
    "tags": ColumnDef(
        label="Tags", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="list_distinct(list(tg.name)) FILTER (WHERE tg.name IS NOT NULL) AS tags",
        join_sql=_J_TAGS,
    ),
    "steam_categories": ColumnDef(
        label="Steam categories", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="any_value(sad.categories) AS steam_categories",
        join_sql=_J_STEAM_DET,
    ),
    "achievement_pct": ColumnDef(
        label="Achievement %", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="MAX(ach.completion_pct) AS achievement_pct",
        join_sql=_J_ACH,
        default=True,
    ),
    "achievements_count": ColumnDef(
        label="Achievements (earned/total)", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql=(
            "CASE WHEN MAX(ach.total_count) > 0 "
            "THEN CAST(MAX(ach.unlocked_count) AS VARCHAR) || '/' || CAST(MAX(ach.total_count) AS VARCHAR) "
            "ELSE NULL END AS achievements_count"
        ),
        join_sql=_J_ACH,
    ),
    "my_review": ColumnDef(
        label="My review", group=_GRP_PLAT,
        platforms=frozenset({"steam"}),
        select_sql="any_value(rv.review_text) AS my_review",
        join_sql=_J_REV,
    ),
    # ── Platform data: PSN ────────────────────────────────────────────────────
    "psn_platform": ColumnDef(
        label="PS Platform (PS4/PS5)", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql="any_value(spsn.platform) AS psn_platform",
        join_sql=_J_PSN,
    ),
    "acquisition_type": ColumnDef(
        label="Acquisition type", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql="any_value(spsn.acquisition_type) AS acquisition_type",
        join_sql=_J_PSN,
    ),
    "trophy_pct": ColumnDef(
        label="Trophy progress %", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql="MAX(spsn.trophy_progress) AS trophy_pct",
        join_sql=_J_PSN,
    ),
    "trophies_count": ColumnDef(
        label="Trophies (earned/defined)", group=_GRP_PLAT,
        platforms=frozenset({"psn"}),
        select_sql=(
            "CASE WHEN MAX(spsn.trophies_defined) > 0 "
            "THEN CAST(MAX(spsn.trophies_earned) AS VARCHAR) || '/' || CAST(MAX(spsn.trophies_defined) AS VARCHAR) "
            "ELSE NULL END AS trophies_count"
        ),
        join_sql=_J_PSN,
    ),
}


def _resolve_col_sql(col: ColumnDef, platform: Optional[str]) -> tuple[str, str]:
    sel = col.select_sql if isinstance(col.select_sql, str) else col.select_sql.get(platform or "", "")
    j   = col.join_sql
    if isinstance(j, dict):
        j = j.get(platform or "", "")
    return sel or "", j or ""


def _build_list_query(
    platform: Optional[str],
    col_keys: list[str],
    q: Optional[str],
    show_hidden: bool,
) -> tuple[str, list]:
    selects = [
        "g.id AS game_id",
        "g.title",
        "list_distinct(list(pl.slug)) AS platforms",
        "any_value(ugp.rating) AS rating",
        "COALESCE(any_value(ugp.hidden), FALSE) AS hidden",
    ]
    extra_joins: list[str] = []
    seen_joins:  set[str]  = set()

    for key in col_keys:
        col = COLUMN_REGISTRY.get(key)
        if col is None or (platform and platform not in col.platforms):
            continue
        sel, j = _resolve_col_sql(col, platform)
        if sel:
            selects.append(sel)
        if j and j not in seen_joins:
            extra_joins.append(j)
            seen_joins.add(j)

    params: list       = [show_hidden]
    where_parts        = ["(? OR NOT COALESCE(ugp.hidden, FALSE))"]

    if platform:
        where_parts.append("pl.slug = ?")
        params.append(platform)

    if q:
        where_parts.append("lower(g.title) LIKE ?")
        params.append(f"%{q.lower()}%")

    sql = (
        f"SELECT {', '.join(selects)}\n"
        "FROM games g\n"
        "JOIN platform_games pg ON pg.game_id = g.id\n"
        "JOIN platforms pl ON pl.id = pg.platform_id\n"
        "JOIN library l ON l.platform_game_id = pg.id\n"
        "LEFT JOIN user_game_prefs ugp ON ugp.game_id = g.id\n"
        + ("\n".join(extra_joins) + "\n" if extra_joins else "")
        + f"WHERE {' AND '.join(where_parts)}\n"
        "GROUP BY g.id, g.title\n"
        "ORDER BY lower(g.title)"
    )
    return sql, params


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RatingBody(BaseModel):
    rating: Optional[str] = None


class HiddenBody(BaseModel):
    hidden: bool


class MergeBody(BaseModel):
    game_id_a: int
    game_id_b: int
    preferred_title: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/library")
async def library(request: Request, show_hidden: bool = False):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    with get_db() as conn:
        last_synced = _last_synced(conn)
        games = _query(conn, """
            SELECT
                cg.id                                                  AS game_id,
                cg.title,
                cg.cover_url,
                list_distinct(list(pl.slug))                           AS platforms,
                MAX(l.playtime_mins)                                   AS playtime_mins,
                MAX(CASE WHEN pl.slug = 'steam'  THEN l.playtime_mins END) AS steam_playtime_mins,
                MAX(CASE WHEN pl.slug = 'switch' THEN l.playtime_mins END) AS switch_playtime_mins,
                bool_and(l.never_launched)                             AS never_launched,
                COALESCE(MAX(a.completion_pct), 0.0)                   AS achievement_pct,
                COALESCE(MAX(spsn.trophy_progress), 0)                 AS trophy_pct,
                bool_or(w.id IS NOT NULL)                              AS on_wishlist,
                list_distinct(list(gn.name))                           AS genres,
                COALESCE(bool_or(sa.platform_id = 1 AND sa.available), FALSE) AS available_on_steam,
                COALESCE(bool_or(sa.platform_id = 3 AND sa.available), FALSE) AS available_on_gog,
                ugp.rating,
                COALESCE(ugp.hidden, FALSE)                            AS hidden
            FROM games g
            JOIN games cg           ON cg.id = COALESCE(g.merged_into, g.id)
            JOIN platform_games pg  ON pg.game_id = g.id
            JOIN platforms pl       ON pl.id = pg.platform_id
            JOIN library l          ON l.platform_game_id = pg.id
            LEFT JOIN achievements a   ON a.platform_game_id = pg.id
            LEFT JOIN wishlist w       ON w.platform_game_id = pg.id
            LEFT JOIN game_genres gg   ON gg.game_id = cg.id
            LEFT JOIN genres gn        ON gn.id = gg.genre_id
            LEFT JOIN store_availability sa ON sa.game_id = cg.id
            LEFT JOIN user_game_prefs ugp   ON ugp.game_id = cg.id
            LEFT JOIN stg_psn_library spsn  ON spsn.np_communication_id = pg.external_id
            WHERE cg.merged_into IS NULL
              AND (? OR NOT COALESCE(ugp.hidden, FALSE))
            GROUP BY cg.id, cg.title, cg.cover_url, ugp.rating, ugp.hidden
            ORDER BY MAX(l.playtime_mins) DESC NULLS LAST
        """, [show_hidden])

    sync_running = sys.modules["main"]._sync_running
    return templates.TemplateResponse(request, "library.html", {
        "user":         user,
        "games":        games,
        "last_synced":  last_synced,
        "sync_running": sync_running,
        "show_hidden":  show_hidden,
    })


@router.get("/profile")
async def profile(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    with get_db() as conn:
        stats = _query(conn, """
            SELECT
                COUNT(DISTINCT g.id)                                         AS total_owned,
                ROUND(SUM(l.playtime_mins) / 60.0, 1)                       AS total_hours,
                SUM(CASE WHEN l.never_launched THEN 1 ELSE 0 END)           AS never_launched
            FROM library l
            JOIN platform_games pg ON pg.id = l.platform_game_id
            JOIN games g            ON g.id  = pg.game_id
        """)[0]

        top_genres = _query(conn, """
            SELECT
                gn.name,
                ROUND(SUM(l.playtime_mins * (1 + COALESCE(a.completion_pct, 0) / 100)) / 60.0, 1)
                    AS weighted_hours
            FROM library l
            JOIN platform_games pg ON pg.id = l.platform_game_id
            JOIN games g            ON g.id  = pg.game_id
            JOIN game_genres gg     ON gg.game_id = g.id
            JOIN genres gn          ON gn.id = gg.genre_id
            LEFT JOIN achievements a ON a.platform_game_id = pg.id
            GROUP BY gn.name
            ORDER BY weighted_hours DESC
            LIMIT 5
        """)

    return templates.TemplateResponse(request, "profile.html", {
        "user":        user,
        "stats":       stats,
        "top_genres":  top_genres,
    })


@router.put("/library/games/{game_id}/rating")
async def set_rating(request: Request, game_id: int, body: RatingBody):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    rating = body.rating
    if rating not in (None, "up", "down"):
        return JSONResponse({"error": "invalid rating"}, status_code=400)

    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_game_prefs (game_id, rating, updated_at)
            VALUES (?, ?, current_timestamp)
            ON CONFLICT (game_id) DO UPDATE SET
                rating     = excluded.rating,
                updated_at = excluded.updated_at
        """, [game_id, rating])

    return JSONResponse({"game_id": game_id, "rating": rating})


@router.put("/library/games/{game_id}/hidden")
async def set_hidden(request: Request, game_id: int, body: HiddenBody):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_game_prefs (game_id, hidden, updated_at)
            VALUES (?, ?, current_timestamp)
            ON CONFLICT (game_id) DO UPDATE SET
                hidden     = excluded.hidden,
                updated_at = excluded.updated_at
        """, [game_id, body.hidden])

    return JSONResponse({"game_id": game_id, "hidden": body.hidden})


@router.get("/api/library/columns")
async def api_library_columns(request: Request, platform: str = ""):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    if not platform:
        return JSONResponse({"platform": "", "groups": []})

    groups: dict[str, list] = {}
    for key, col in COLUMN_REGISTRY.items():
        if platform not in col.platforms:
            continue
        groups.setdefault(col.group, []).append({
            "key":     key,
            "label":   col.label,
            "default": col.default,
        })

    return JSONResponse({
        "platform": platform,
        "groups": [{"label": label, "columns": cols} for label, cols in groups.items()],
    })


@router.get("/api/library/games")
async def api_library_games(
    request: Request,
    platform:    str  = "",
    columns:     str  = "",
    q:           str  = "",
    show_hidden: bool = False,
):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    col_keys = [c.strip() for c in columns.split(",") if c.strip()] if columns else []
    sql, params = _build_list_query(platform or None, col_keys, q or None, show_hidden)

    with get_db() as conn:
        rows = _query(conn, sql, params)

    return JSONResponse({"games": rows})


@router.post("/library/games/merge")
async def merge_games(request: Request, body: MergeBody):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    a, b = body.game_id_a, body.game_id_b
    if a == b:
        return JSONResponse({"error": "cannot merge a game with itself"}, status_code=400)

    with get_db() as conn:
        counts = _query(
            conn,
            "SELECT game_id, COUNT(*) AS n FROM platform_games WHERE game_id IN (?, ?) GROUP BY game_id",
            [a, b],
        )
        count_map = {r["game_id"]: r["n"] for r in counts}
        na, nb    = count_map.get(a, 0), count_map.get(b, 0)
        survive   = a if na > nb or (na == nb and a < b) else b
        discard   = b if survive == a else a

        chosen_title = (body.preferred_title or "").strip() or None

        rows = _query(conn, "SELECT id, title, cover_url, igdb_id FROM games WHERE id IN (?, ?)", [survive, discard])
        if len(rows) < 2:
            return JSONResponse({"error": f"one or both game IDs not found: {a}, {b}"}, status_code=404)
        row_map = {r["id"]: r for r in rows}
        sv, dc  = row_map[survive], row_map[discard]

        final_title = chosen_title or sv["title"]
        final_cover = sv["cover_url"] or dc["cover_url"]
        final_igdb  = sv["igdb_id"]   or dc["igdb_id"]

        try:
            conn.execute("BEGIN")
            conn.execute(
                "UPDATE games SET title = ?, cover_url = ?, igdb_id = ? WHERE id = ?",
                [final_title, final_cover, final_igdb, survive],
            )
            conn.execute(
                "INSERT INTO game_tags (game_id, tag_id) SELECT ?, tag_id FROM game_tags WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            conn.execute(
                "INSERT INTO game_genres (game_id, genre_id) SELECT ?, genre_id FROM game_genres WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            conn.execute(
                "INSERT INTO store_availability (game_id, platform_id, available, external_id, checked_at) "
                "SELECT ?, platform_id, available, external_id, checked_at FROM store_availability WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            conn.execute(
                "INSERT INTO user_game_prefs (game_id, rating, hidden, updated_at) "
                "SELECT ?, rating, hidden, updated_at FROM user_game_prefs WHERE game_id = ? ON CONFLICT DO NOTHING",
                [survive, discard],
            )
            for table in ("game_tags", "game_genres", "store_availability", "user_game_prefs"):
                conn.execute(f"DELETE FROM {table} WHERE game_id = ?", [discard])
            conn.execute("UPDATE games SET merged_into = ? WHERE id = ?", [survive, discard])
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            logger.exception("merge_games failed: survive=%s discard=%s", survive, discard)
            return JSONResponse({"error": "merge failed"}, status_code=500)

    return JSONResponse({"surviving_game_id": survive})
