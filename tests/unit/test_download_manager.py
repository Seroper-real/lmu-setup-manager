import threading
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def dm(tmp_path, in_memory_db, mocker):
    mocker.patch("orchestration.download_manager.DOWNLOAD_PATH", tmp_path)
    mocker.patch("orchestration.download_manager.TrackTitanClient")
    from orchestration.download_manager import DownloadManager
    return DownloadManager(database=in_memory_db)


def test_uuid_extracted_from_zip_filename(tmp_path, in_memory_db, mocker):
    mocker.patch("orchestration.download_manager.DOWNLOAD_PATH", tmp_path)
    mocker.patch("orchestration.download_manager.TrackTitanClient")
    (tmp_path / "Spa_Francorchamps-uuid-1234.zip").touch()
    (tmp_path / "not_a_zip.txt").touch()
    from orchestration.download_manager import DownloadManager
    manager = DownloadManager(database=in_memory_db)
    assert len(manager.already_downloaded) == 1


def test_empty_dir_no_downloaded(dm):
    assert len(dm.already_downloaded) == 0


def test_get_setups_list_returns_setup_objects(dm, sample_setup_data):
    from domain.setup import Setup
    dm.track_titan_client.get.return_value = {"data": {"setups": [sample_setup_data, sample_setup_data]}}
    dm.track_titan_client.throttle.return_value = None
    result = dm.get_setups_list()
    assert len(result) == 2
    assert all(isinstance(s, Setup) for s in result)


def test_get_setups_list_sets_finished_on_partial_page(dm, sample_setup_data):
    dm.page_size = 12
    dm.track_titan_client.get.return_value = {"data": {"setups": [sample_setup_data] * 5}}
    dm.track_titan_client.throttle.return_value = None
    dm.get_setups_list()
    assert dm.finished is True


def test_get_setups_list_empty_when_finished(dm):
    dm.finished = True
    assert dm.get_setups_list() == []


def test_page_size_comes_from_config(dm):
    import core.config as config
    assert dm.page_size == config.PAGE_SIZE


def test_restart_resets_pagination(dm):
    dm.page = 5
    dm.finished = True
    dm.restart_setups_list()
    assert dm.page == 1
    assert dm.finished is False


def test_download_skips_if_already_installed(dm, sample_setup, mocker):
    mocker.patch.object(dm.database, "is_setup_installed_last_version", return_value=True)
    assert dm.download(sample_setup) is None


def test_injected_client_is_used_and_real_client_not_built(tmp_path, in_memory_db, mocker):
    mocker.patch("orchestration.download_manager.DOWNLOAD_PATH", tmp_path)
    real = mocker.patch("orchestration.download_manager.TrackTitanClient")
    injected = MagicMock()

    from orchestration.download_manager import DownloadManager
    manager = DownloadManager(database=in_memory_db, client=injected)

    assert manager.track_titan_client is injected
    real.assert_not_called()


def test_omitted_client_falls_back_to_real_client(tmp_path, in_memory_db, mocker):
    mocker.patch("orchestration.download_manager.DOWNLOAD_PATH", tmp_path)
    real = mocker.patch("orchestration.download_manager.TrackTitanClient")

    from orchestration.download_manager import DownloadManager
    DownloadManager(database=in_memory_db)

    real.assert_called_once()


def test_download_writes_zip_file(dm, sample_setup, mocker, tmp_path):
    mocker.patch.object(dm.database, "is_setup_installed_last_version", return_value=False)
    mock_client = dm.track_titan_client
    mock_client.download_link.return_value = {"url": "https://cdn.example.com/file.zip"}
    mock_resp = MagicMock()
    mock_resp.content = b"zip bytes"
    mock_client.download.return_value = mock_resp
    mock_client.throttle.return_value = None

    result = dm.download(sample_setup)

    assert result is not None
    assert result.suffix == ".zip"
    assert result.exists()
    assert result.read_bytes() == b"zip bytes"


def _stub_download(dm, mocker):
    mocker.patch.object(dm.database, "is_setup_installed_last_version", return_value=False)
    client = dm.track_titan_client
    client.download_link.return_value = {"url": "https://cdn.example.com/file.zip"}
    resp = MagicMock()
    resp.content = b"zip bytes"
    client.download.return_value = resp
    client.throttle.return_value = None
    return client


def test_download_caches_whole_setup_id(dm, sample_setup, mocker):
    """set.update(str) would scatter the id's characters into the cache."""
    _stub_download(dm, mocker)

    dm.download(sample_setup)

    assert dm.already_downloaded == {sample_setup.id}


def test_second_download_in_same_run_hits_the_cache(dm, sample_setup, mocker):
    client = _stub_download(dm, mocker)

    dm.download(sample_setup)
    dm.download(sample_setup)

    client.download_link.assert_called_once()


# --- cancel_event ------------------------------------------------------------


def test_cancel_event_defaults_to_none(dm):
    assert dm.cancel_event is None


def test_get_setups_list_empty_when_cancelled(dm):
    dm.cancel_event = threading.Event()
    dm.cancel_event.set()

    assert dm.get_setups_list() == []
    dm.track_titan_client.get.assert_not_called()


def test_get_setups_list_runs_normally_when_cancel_event_not_set(dm, sample_setup_data):
    dm.cancel_event = threading.Event()  # constructed but never set
    dm.track_titan_client.get.return_value = {"data": {"setups": [sample_setup_data]}}
    dm.track_titan_client.throttle.return_value = None

    result = dm.get_setups_list()

    assert len(result) == 1


def test_cancel_event_passed_at_construction_is_honored(tmp_path, in_memory_db, mocker):
    mocker.patch("orchestration.download_manager.DOWNLOAD_PATH", tmp_path)
    mocker.patch("orchestration.download_manager.TrackTitanClient")
    from orchestration.download_manager import DownloadManager

    event = threading.Event()
    event.set()
    manager = DownloadManager(database=in_memory_db, cancel_event=event)

    assert manager.get_setups_list() == []
