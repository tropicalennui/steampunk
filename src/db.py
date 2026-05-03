import json
import duckdb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "steampunk.duckdb"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SECRETS_PATH = ROOT / "gandalf.json"


def load_secrets() -> dict:
    with open(SECRETS_PATH) as f:
        return json.load(f)


def _deep_merge(base: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def save_secrets(updates: dict) -> None:
    data = load_secrets()
    _deep_merge(data, updates)
    with open(SECRETS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def init_db() -> None:
    schema_sql = SCHEMA_PATH.read_text()
    conn = connect()
    for stmt in schema_sql.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.close()
