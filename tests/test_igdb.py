"""Unit tests for igdb_lookup_by_external_id — HTTP calls are mocked."""
from unittest.mock import MagicMock, patch

from collect import igdb_lookup_by_external_id

_TOKEN = "fake-igdb-token"
_CLIENT_ID = "fake-client-id"
_CATEGORY = 1  # Steam
_UID = "570"


def _mock_response(ok: bool, json_data) -> MagicMock:
    resp = MagicMock()
    resp.ok = ok
    resp.json.return_value = json_data
    return resp


def test_igdb_lookup_returns_game_id_on_match():
    mock_resp = _mock_response(ok=True, json_data=[{"game": 1942}])
    with patch("collect.requests.post", return_value=mock_resp) as mock_post:
        result = igdb_lookup_by_external_id(_TOKEN, _CLIENT_ID, _CATEGORY, _UID)
    assert result == 1942
    mock_post.assert_called_once()


def test_igdb_lookup_returns_none_on_empty_response():
    mock_resp = _mock_response(ok=True, json_data=[])
    with patch("collect.requests.post", return_value=mock_resp):
        result = igdb_lookup_by_external_id(_TOKEN, _CLIENT_ID, _CATEGORY, _UID)
    assert result is None


def test_igdb_lookup_returns_none_on_http_error():
    mock_resp = _mock_response(ok=False, json_data=[])
    with patch("collect.requests.post", return_value=mock_resp):
        result = igdb_lookup_by_external_id(_TOKEN, _CLIENT_ID, _CATEGORY, _UID)
    assert result is None
