"""DownloadManager._reuse_cached_archive and the stale-cache handling in download().

already_downloaded only records ids sliced from any .zip name in DOWNLOAD_PATH, so
download() must verify the expected archive actually exists before trusting it.
"""
from unittest.mock import MagicMock

import pytest

SID = "0a1b2c3d-0000-4000-8000-000000000001"


@pytest.fixture
def dm(tmp_path, mocker):
    mocker.patch("orchestration.download_manager.DOWNLOAD_PATH", tmp_path)
    mocker.patch("orchestration.download_manager.TrackTitanClient")
    from orchestration.download_manager import DownloadManager
    return DownloadManager(database=None)


def _setup(sample_setup_data):
    from domain.setup import Setup
    return Setup({**sample_setup_data, "id": SID})


def test_reuse_true_when_expected_file_exists(dm, tmp_path):
    path = tmp_path / f"HYMO-Spa-{SID}.zip"
    path.write_bytes(b"x")
    assert dm._reuse_cached_archive(SID, path) is True
    assert path.read_bytes() == b"x"


def test_reuse_moves_renamed_leftover(dm, tmp_path):
    leftover = tmp_path / f"HYMO-Spa _ WEC-{SID}.zip"
    leftover.write_bytes(b"data")
    path = tmp_path / f"HYMO-Spa-{SID}.zip"
    assert dm._reuse_cached_archive(SID, path) is True
    assert path.read_bytes() == b"data"
    assert not leftover.exists()


def test_reuse_false_when_nothing_usable(dm, tmp_path):
    (tmp_path / f"dual-{SID}.zip").write_bytes(b"staged")
    (tmp_path / "HYMO-Spa-other-id.zip").write_bytes(b"other")
    path = tmp_path / f"HYMO-Spa-{SID}.zip"
    assert dm._reuse_cached_archive(SID, path) is False
    assert not path.exists()
    assert (tmp_path / f"dual-{SID}.zip").exists()  # staging copy is never taken


def test_download_redownloads_when_id_cached_but_file_missing(dm, tmp_path, sample_setup_data):
    (tmp_path / f"dual-{SID}.zip").write_bytes(b"staged")
    dm.get_downloaded_setup_uuid()
    assert SID in dm.already_downloaded
    client = dm.track_titan_client
    client.download_link.return_value = dict(url="u")
    client.download.return_value = MagicMock(content=b"fresh")

    path = dm.download(_setup(sample_setup_data))

    client.download_link.assert_called_once_with(SID)
    assert path.read_bytes() == b"fresh"


def test_download_reuses_renamed_leftover_without_network(dm, tmp_path, sample_setup_data):
    (tmp_path / f"HYMO-Raw Track _ WEC-{SID}.zip").write_bytes(b"cached")
    dm.get_downloaded_setup_uuid()

    path = dm.download(_setup(sample_setup_data))

    dm.track_titan_client.download_link.assert_not_called()
    assert path.exists() and path.read_bytes() == b"cached"
