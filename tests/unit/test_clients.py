import pytest


def test_mock_tracktitan_returned_and_real_client_never_built(tmp_path, mocker, monkeypatch):
    import clients.mocks.mock_track_titan_client as mtt
    from clients.mocks.mock_track_titan_client import MockTrackTitanClient

    _write_catalog(tmp_path)
    monkeypatch.setattr(mtt, "SANDBOX_TRACKTITAN_PATH", tmp_path)
    mocker.patch("clients.protocols.MOCK_TRACKTITAN", True)
    real = mocker.patch("clients.track_titan_client.TrackTitanClient")

    from clients.protocols import build_track_titan_client
    client = build_track_titan_client()

    assert isinstance(client, MockTrackTitanClient)
    real.assert_not_called()


def test_real_tracktitan_returned_when_not_mocked(mocker):
    mocker.patch("clients.protocols.MOCK_TRACKTITAN", False)
    real = mocker.patch("clients.track_titan_client.TrackTitanClient")

    from clients.protocols import build_track_titan_client
    build_track_titan_client()

    real.assert_called_once()


def test_mock_dropbox_returned_and_real_client_never_built(tmp_path, mocker, monkeypatch):
    import clients.mocks.mock_dropbox_client as mdb
    from clients.mocks.mock_dropbox_client import MockDropboxClient

    monkeypatch.setattr(mdb, "SANDBOX_DROPBOX_PATH", tmp_path / "share")
    mocker.patch("clients.protocols.MOCK_DROPBOX", True)
    real = mocker.patch("clients.dropbox_client.DropboxClient")

    from clients.protocols import build_dropbox_client
    client = build_dropbox_client()

    assert isinstance(client, MockDropboxClient)
    real.assert_not_called()


def test_real_dropbox_returned_when_not_mocked(mocker):
    mocker.patch("clients.protocols.MOCK_DROPBOX", False)
    real = mocker.patch("clients.dropbox_client.DropboxClient")

    from clients.protocols import build_dropbox_client
    build_dropbox_client()

    real.assert_called_once()


@pytest.mark.parametrize("cls_path,protocol_name", [
    ("clients.mocks.mock_track_titan_client.MockTrackTitanClient", "TrackTitanClientProtocol"),
    ("clients.track_titan_client.TrackTitanClient", "TrackTitanClientProtocol"),
    ("clients.mocks.mock_dropbox_client.MockDropboxClient", "DropboxClientProtocol"),
    ("clients.dropbox_client.DropboxClient", "DropboxClientProtocol"),
])
def test_clients_satisfy_their_protocol(cls_path, protocol_name):
    """The mock and the real client must be interchangeable at the seam."""
    import importlib
    import clients.protocols as clients

    module_name, cls_name = cls_path.rsplit(".", 1)
    cls = getattr(importlib.import_module(module_name), cls_name)
    protocol = getattr(clients, protocol_name)

    # runtime_checkable Protocols check method presence, which is the contract
    # the managers rely on.
    assert isinstance(cls.__new__(cls), protocol)


def _write_catalog(base):
    import json
    (base / "catalog.json").write_text(json.dumps({"data": {"setups": []}}), encoding="utf-8")
