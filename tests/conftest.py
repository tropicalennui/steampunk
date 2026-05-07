import atexit
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import duckdb
import pytest

# ── sys.path ──────────────────────────────────────────────────────────────────
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── Temp file setup — must happen before importing db or main ─────────────────
_temp_dir = tempfile.mkdtemp(prefix="steampunk_test_")
FAKE_SECRETS_PATH = Path(_temp_dir) / "gandalf.json"
FAKE_DB_PATH = Path(_temp_dir) / "test.duckdb"

FAKE_SECRETS: dict = {
    "app": {"session_secret": "test-secret-key-xxxxxxxxxxxxxxxxxxx", "timezone": "UTC"},
    "steam": {
        "api_key": "test-api-key",
        "steam_id64": "76561198000000001",
        "session_cookie": "test-cookie",
    },
    "gog": {},
    "psn": {},
    "switch": {},
    "xbox": {},
    "igdb": {},
    "sonarqube": {},
}
FAKE_SECRETS_PATH.write_text(json.dumps(FAKE_SECRETS))

# Patch db module attributes BEFORE importing main so init_db() and
# load_secrets() use the test paths for the entire session.
import db as _db_module  # noqa: E402

_db_module.SECRETS_PATH = FAKE_SECRETS_PATH
_db_module.DB_PATH = FAKE_DB_PATH

# Now import main — it calls load_secrets() and init_db() at module level,
# both of which will use the patched paths above.
import main as _main_module  # noqa: E402

_main_module.DB_PATH = FAKE_DB_PATH

atexit.register(shutil.rmtree, _temp_dir, True)

# ── Shared constants ──────────────────────────────────────────────────────────
SCHEMA_SQL = (_SRC / "schema.sql").read_text()


# ── Xbox mock types ───────────────────────────────────────────────────────────

@dataclass
class MockAchievement:
    current_achievements: int
    total_achievements: int
    current_gamerscore: int
    total_gamerscore: int


@dataclass
class MockTitleHistory:
    last_time_played: Optional[datetime]


@dataclass
class MockXboxTitle:
    title_id: int
    name: str
    achievement: Optional[MockAchievement]
    title_history: Optional[MockTitleHistory]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_conn():
    """Fresh in-memory DuckDB with schema applied — isolated per test."""
    conn = duckdb.connect(":memory:")
    for stmt in SCHEMA_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    yield conn
    conn.close()


@pytest.fixture
def unauth_client(monkeypatch):
    """TestClient where _user returns None (not logged in)."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(_main_module, "_user", lambda req: None)
    monkeypatch.setattr(_main_module, "_run_sync", lambda platforms=None: None)
    with TestClient(_main_module.app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def client(monkeypatch):
    """FastAPI TestClient with a fake authenticated session and a no-op _run_sync."""
    from fastapi.testclient import TestClient

    _fake_user = {"steam_id": "76561198000000001", "name": "TestUser", "avatar": ""}
    monkeypatch.setattr(_main_module, "_user", lambda req: _fake_user)
    monkeypatch.setattr(_main_module, "_run_sync", lambda platforms=None: None)

    with TestClient(_main_module.app, raise_server_exceptions=True) as c:
        yield c
