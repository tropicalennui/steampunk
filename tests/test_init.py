"""Tests for src/init.py — ensure_gandalf_initialised."""
import json
from unittest.mock import patch

import init


def test_ensure_gandalf_skips_when_file_exists(tmp_path):
    fake_path = tmp_path / "gandalf.json"
    fake_path.write_text('{"existing": true}')
    with patch.object(init, "SECRETS_PATH", fake_path):
        init.ensure_gandalf_initialised()
    data = json.loads(fake_path.read_text())
    assert "existing" in data  # file was not overwritten


def test_ensure_gandalf_creates_file_when_missing(tmp_path):
    fake_path = tmp_path / "gandalf.json"
    with patch.object(init, "SECRETS_PATH", fake_path):
        init.ensure_gandalf_initialised()
    assert fake_path.exists()
    data = json.loads(fake_path.read_text())
    assert "steam" in data
    assert "app" in data
    assert "session_secret" in data["app"]


def test_ensure_gandalf_writes_bundled_credentials_when_available(tmp_path):
    fake_path = tmp_path / "gandalf.json"
    mock_creds = {
        "GOG_CLIENT_ID": "gog-cid",
        "GOG_CLIENT_SECRET": "gog-sec",
        "IGDB_CLIENT_ID": "igdb-cid",
        "IGDB_CLIENT_SECRET": "igdb-sec",
    }
    fake_module = type("bundled_credentials", (), mock_creds)
    with patch.object(init, "SECRETS_PATH", fake_path), \
         patch.dict("sys.modules", {"bundled_credentials": fake_module}):
        init.ensure_gandalf_initialised()
    data = json.loads(fake_path.read_text())
    assert data["gog"]["client_id"] == "gog-cid"
    assert data["igdb"]["client_id"] == "igdb-cid"
