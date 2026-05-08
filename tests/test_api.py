"""API route smoke tests — uses the shared TestClient fixture from conftest."""
import main


def test_get_library_returns_200(client):
    response = client.get("/library")
    assert response.status_code == 200


def test_get_setup_returns_200(client):
    response = client.get("/setup")
    assert response.status_code == 200


def test_get_setup_shows_disconnected_state(client):
    # Fake secrets have no GOG/PSN/Xbox tokens, so all services are disconnected.
    response = client.get("/setup")
    assert response.status_code == 200
    # The template context passes gog_connected=False; the page should not show
    # a "connected" indicator for GOG.
    assert "gog_connected=1" not in str(response.url)


def test_post_sync_redirects_to_logs(client):
    response = client.post("/sync", data={"platforms": "all"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/logs"


def test_post_sync_while_running_redirects_to_logs(client, monkeypatch):
    monkeypatch.setattr(main, "_sync_running", True)
    response = client.post("/sync", data={"platforms": "all"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/logs"


def test_get_api_library_columns_returns_expected_shape(client):
    response = client.get("/api/library/columns", params={"platform": "steam"})
    assert response.status_code == 200
    body = response.json()
    assert "platform" in body
    assert body["platform"] == "steam"
    assert "groups" in body
    assert isinstance(body["groups"], list)
    assert len(body["groups"]) > 0
    # Each group has a label and a list of column defs
    for group in body["groups"]:
        assert "label" in group
        assert "columns" in group
        for col in group["columns"]:
            assert "key" in col
            assert "label" in col
            assert "default" in col
