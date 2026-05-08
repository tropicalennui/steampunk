"""Shared, non-patchable application state imported by main.py and the routers."""
import duckdb
from contextlib import contextmanager
from pathlib import Path

from fastapi.templating import Jinja2Templates

import db as _db

ROOT          = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR    = ROOT / "static"
SRC_DIR       = Path(__file__).resolve().parent
LOGS_DIR      = ROOT / "logs"

MAX_LOG_FILES = 10
_LOG_GLOB     = "sync_*.log"

_URL_LIBRARY          = "/library"
_URL_SETUP            = "/setup"
_URL_WIZARD_STEAM_API = "/wizard/steam-api"

# Loaded once at startup; routers may mutate nested keys (e.g. secrets["app"]["timezone"])
secrets   = _db.load_secrets()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["timezone"] = secrets["app"].get("timezone", "UTC")


@contextmanager
def get_db():
    conn = duckdb.connect(str(_db.DB_PATH))
    try:
        yield conn
    finally:
        conn.close()


def _query(conn: duckdb.DuckDBPyConnection, sql: str, params=None) -> list[dict]:
    result = conn.execute(sql, params or [])
    cols   = [d[0] for d in result.description]
    return [dict(zip(cols, row)) for row in result.fetchall()]


def _last_synced(conn: duckdb.DuckDBPyConnection) -> str | None:
    rows = _query(conn, "SELECT MAX(collected_at) AS ts FROM stg_steam_library")
    ts   = rows[0]["ts"] if rows else None
    if ts is None:
        return None
    return str(ts).replace(" ", "T").split(".")[0] + "Z"
