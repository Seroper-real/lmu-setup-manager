from pathlib import Path

import pytest


@pytest.fixture
def share(tmp_path):
    return tmp_path / "share"


@pytest.fixture
def client(share):
    from clients.mocks.mock_dropbox_client import MockDropboxClient
    return MockDropboxClient(folder=share)


@pytest.fixture
def package(tmp_path):
    p = tmp_path / "package.zip"
    p.write_bytes(b"zip payload")
    return p


def test_constructor_creates_share_folder(client, share):
    assert share.is_dir()


def test_empty_share_lists_nothing(client):
    assert client.list_setups() == []


def test_upload_then_list(client, package):
    client.upload(package, "HYMO-Spa_Porsche963_uuid-1_1700000000.zip")

    listed = client.list_setups()
    assert len(listed) == 1
    assert listed[0].name == "HYMO-Spa_Porsche963_uuid-1_1700000000.zip"
    assert listed[0].setup_id == "uuid-1"
    assert listed[0].ts == 1700000000


def test_upload_creates_nested_car_subfolder(client, package, share):
    client.upload(package, "Porsche_963/HYMO-Spa_Porsche963_uuid-1_1700000000.zip")

    assert (share / "Porsche_963" / "HYMO-Spa_Porsche963_uuid-1_1700000000.zip").is_file()
    listed = client.list_setups()
    assert len(listed) == 1
    assert listed[0].name == "HYMO-Spa_Porsche963_uuid-1_1700000000.zip"
    assert listed[0].setup_id == "uuid-1"
    assert listed[0].ts == 1700000000


def test_round_trip_upload_download_delete(client, package, tmp_path):
    client.upload(package, "HYMO-Spa_Porsche963_uuid-1_1700000000.zip")
    remote = client.list_setups()[0]

    local = tmp_path / "pulled" / "copy.zip"
    returned = client.download_to(remote.path_lower, local)

    assert returned == local
    assert local.read_bytes() == b"zip payload"

    client.delete(remote.path_lower)
    assert client.list_setups() == []


def test_non_conforming_names_are_skipped(client, share, caplog):
    (share / "not-a-setup.zip").write_bytes(b"x")
    (share / "notes.txt").write_bytes(b"x")

    with caplog.at_level("WARNING"):
        assert client.list_setups() == []
    assert "not-a-setup.zip" in caplog.text


def test_files_without_hymo_prefix_are_skipped(client, share, caplog):
    """A conforming name lacking the HYMO- brand (e.g. manually dropped by a
    human) must not be picked up."""
    (share / "Spa_Porsche963_uuid-1_1700000000.zip").write_bytes(b"x")

    with caplog.at_level("WARNING"):
        assert client.list_setups() == []


def test_delete_is_idempotent(client, share):
    client.delete(str(share / "absent.zip"))


def test_delete_if_exists_returns_true_and_removes_the_file(client, package):
    client.upload(package, "HYMO-Spa_Porsche963_uuid-1_1700000000.zip")
    remote = client.list_setups()[0]

    assert client.delete_if_exists(remote.path_lower) is True
    assert client.list_setups() == []


def test_delete_if_exists_returns_false_for_a_missing_file(client, share):
    assert client.delete_if_exists(str(share / "absent.zip")) is False


# ----- GO Setups (list_setups skip, list_go_setups, remote_path, move) ---------


def test_list_setups_skips_go_prefixed_zips_without_warning(client, package, share, caplog):
    client.upload(package, "GO-ORECA.zip")
    client.upload(package, "HYMO-Spa_Porsche963_uuid-1_1700000000.zip")
    caplog.clear()

    with caplog.at_level("WARNING"):
        setups = client.list_setups()

    assert len(setups) == 1
    assert setups[0].setup_id == "uuid-1"
    assert "GO-ORECA.zip" not in caplog.text


def test_list_go_setups_parses_car_track_from_folder_structure(client, package):
    client.upload(package, "Oreca 07/Imola/GO-ORECA.zip")

    setups = client.list_go_setups()

    assert len(setups) == 1
    assert setups[0].car == "Oreca 07"
    assert setups[0].track == "Imola"
    assert setups[0].name == "GO-ORECA.zip"


def test_list_go_setups_skips_and_warns_at_wrong_depth(client, package, caplog):
    client.upload(package, "GO-Flat.zip")
    client.upload(package, "a/b/c/GO-TooDeep.zip")

    with caplog.at_level("WARNING"):
        setups = client.list_go_setups()

    assert setups == []
    assert "GO-Flat.zip" in caplog.text
    assert "GO-TooDeep.zip" in caplog.text


def test_list_go_setups_ignores_non_go_zips_regardless_of_depth(client, package, caplog):
    client.upload(package, "Porsche_963/HYMO-Spa_Porsche963_uuid-1_1700000000.zip")
    caplog.clear()

    with caplog.at_level("WARNING"):
        setups = client.list_go_setups()

    assert setups == []
    assert caplog.text == ""


def test_remote_path_round_trips_via_temp_dir(client, share):
    assert client.remote_path("a/b/x.zip") == str((share / "a" / "b" / "x.zip").resolve())


def test_move_round_trips_via_temp_dir(client, package, share):
    src = share / "old" / "x.zip"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(package.read_bytes())
    dst = client.remote_path("new/x.zip")

    client.move(str(src), dst)

    assert not src.exists()
    assert Path(dst).exists()
