import json
import zipfile

import pytest


@pytest.fixture
def fixtures(tmp_path):
    """A miniature stand-in for sandbox/tracktitan/."""
    setups = [
        {
            "id": f"uuid-{i}",
            "title": f"Setup {i}",
            "setupCombos": [{"car": {"name": "Porsche 963"}, "track": {"name": "Spa"}}],
            "hotlapLink": None,
            "lastUpdatedAt": 1700000000 + i,
            "isBundle": False,
        }
        for i in range(5)
    ]
    (tmp_path / "catalog.json").write_text(json.dumps({"data": {"setups": setups}}), encoding="utf-8")

    setups_dir = tmp_path / "setups"
    setups_dir.mkdir()
    with zipfile.ZipFile(setups_dir / "uuid-0.zip", "w") as zf:
        zf.writestr("a.svm", "data")
    return tmp_path


@pytest.fixture
def client(fixtures):
    from clients.mocks.mock_track_titan_client import MockTrackTitanClient
    return MockTrackTitanClient(base_path=fixtures)


def test_missing_catalog_raises(tmp_path):
    from clients.mocks.mock_track_titan_client import MockTrackTitanClient
    with pytest.raises(RuntimeError, match="catalog not found"):
        MockTrackTitanClient(base_path=tmp_path)


def test_get_returns_api_shaped_payload(client):
    result = client.get("/v2/games/leMansUltimate/setups", params={"page": 1, "limit": 12})
    assert [s["id"] for s in result["data"]["setups"]] == [f"uuid-{i}" for i in range(5)]


def test_get_paginates(client):
    first = client.get("/setups", params={"page": 1, "limit": 2})
    second = client.get("/setups", params={"page": 2, "limit": 2})
    third = client.get("/setups", params={"page": 3, "limit": 2})

    assert [s["id"] for s in first["data"]["setups"]] == ["uuid-0", "uuid-1"]
    assert [s["id"] for s in second["data"]["setups"]] == ["uuid-2", "uuid-3"]
    assert [s["id"] for s in third["data"]["setups"]] == ["uuid-4"]


def test_get_past_last_page_is_empty(client):
    assert client.get("/setups", params={"page": 99, "limit": 12})["data"]["setups"] == []


def test_download_link_round_trips_through_download(client, fixtures):
    url = client.download_link("uuid-0")["url"]
    response = client.download(url)
    assert response.content == (fixtures / "setups" / "uuid-0.zip").read_bytes()


def test_download_rejects_foreign_url(client):
    with pytest.raises(ValueError):
        client.download("https://cdn.example.com/file.zip")


def test_download_missing_archive_raises(client):
    with pytest.raises(FileNotFoundError):
        client.download(client.download_link("uuid-4")["url"])


def test_throttle_does_not_sleep(client, mocker):
    sleep = mocker.patch("time.sleep")
    client.throttle()
    sleep.assert_not_called()


def test_known_setup_ids_returns_every_catalog_id(client):
    assert client.known_setup_ids() == {f"uuid-{i}" for i in range(5)}


def test_known_setup_car_tracks_returns_every_safe_car_track_pair(client):
    # Every fixture setup shares the same car/track in this test's catalog (see
    # the `fixtures` fixture above), so all 5 collapse to one pair - matching
    # how a real GO archive and multiple HYMO setups can share one Dropbox
    # folder (see cleanup_sandbox_go_setups()).
    assert client.known_setup_car_tracks() == {("Porsche 963", "Spa")}


def test_download_prefers_the_sandbox_marked_fixture(client, fixtures):
    # Checked-in fixtures carry a "-SANDBOX" marker (see
    # cleanup_sandbox_dropbox.py); it must be tried before the plain name.
    marked = fixtures / "setups" / "uuid-0-SANDBOX.zip"
    marked.write_bytes(b"sandbox-marked content")

    response = client.download(client.download_link("uuid-0")["url"])

    assert response.content == b"sandbox-marked content"
