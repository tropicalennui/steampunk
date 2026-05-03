import json
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / "gandalf.json"


def ensure_gandalf_initialised() -> None:
    if SECRETS_PATH.exists():
        return

    try:
        from bundled_credentials import (
            GOG_CLIENT_ID,
            GOG_CLIENT_SECRET,
            IGDB_CLIENT_ID,
            IGDB_CLIENT_SECRET,
        )
    except ImportError:
        print(
            "[init] bundled_credentials.py not found — "
            "copy bundled_credentials.example.py and fill in values for local dev."
        )
        GOG_CLIENT_ID = GOG_CLIENT_SECRET = ""
        IGDB_CLIENT_ID = IGDB_CLIENT_SECRET = ""

    initial = {
        "steam": {},
        "gog": {"client_id": GOG_CLIENT_ID, "client_secret": GOG_CLIENT_SECRET},
        "psn": {},
        "switch": {},
        "igdb": {"client_id": IGDB_CLIENT_ID, "client_secret": IGDB_CLIENT_SECRET},
        "app": {
            "session_secret": secrets.token_hex(32),
            "timezone": "UTC",
        },
    }

    with open(SECRETS_PATH, "w") as f:
        json.dump(initial, f, indent=2)

    print(f"[init] Created {SECRETS_PATH}")
