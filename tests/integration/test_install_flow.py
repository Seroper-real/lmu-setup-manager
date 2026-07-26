import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def env(tmp_path, in_memory_db, mocker):
    dl_path = tmp_path / "downloads"
    dl_path.mkdir()
    lmu_path = tmp_path / "lmu"
    lmu_path.mkdir()

    mapping_file = tmp_path / "mapping.json"
    mapping_file.write_text(json.dumps({
        "tracks": [{"name": "Spa", "matcher": ["spa|francorchamps"], "lmu_folder": "Spa"}],
    }), encoding="utf-8")

    mocker.patch("orchestration.download_manager.DOWNLOAD_PATH", dl_path)
    mocker.patch("orchestration.download_manager.TrackTitanClient")
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.track_manager.get_path", return_value=mapping_file)
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=mapping_file)
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.setup_manager.OVERWRITE", True)
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", False)
    mocker.patch("processing.setup_manager.SETUP_FILE_EXTENSIONS", {".svm"})
    mocker.patch("processing.setup_manager.DOWNLOAD_PATH", dl_path)

    from orchestration.download_manager import DownloadManager
    from processing.track_manager import TrackManager
    from processing.car_manager import CarManager
    from processing.setup_manager import SetupManager

    dm = DownloadManager(database=in_memory_db)
    tm = TrackManager()
    cm = CarManager()
    sm = SetupManager(
        database=in_memory_db,
        track_manager=tm,
        car_manager=cm,
        lmu_setups_base_path=lmu_path,
        overwrite=True,
        already_installed=set(),
    )
    return dm, sm, dl_path, lmu_path


def test_full_download_and_install(env, sample_setup_data, mocker):
    dm, sm, dl_path, lmu_path = env
    from domain.setup import Setup
    setup = Setup(sample_setup_data)

    mock_client = dm.track_titan_client
    mock_client.download_link.return_value = {"url": "https://cdn.example.com/file.zip"}
    mock_resp = MagicMock()
    mock_resp.content = b"fake zip"
    mock_client.download.return_value = mock_resp
    mock_client.throttle.return_value = None

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "porsche_spa.svm").write_bytes(b"setup_data")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    path = dm.download(setup)
    assert path is not None

    sm.install_setup(path, setup)

    assert (lmu_path / "Spa" / "porsche_spa.svm").exists()
    assert dm.database.is_setup_installed_last_version(setup) is True


def test_second_download_skipped_when_installed(env, sample_setup_data):
    dm, sm, dl_path, lmu_path = env
    from domain.setup import Setup
    setup = Setup(sample_setup_data)

    dir_ = lmu_path / "Spa"
    dir_.mkdir()
    dm.database.add_installed_setup(setup, [], True, dir_)

    result = dm.download(setup)
    assert result is None
    dm.track_titan_client.download_link.assert_not_called()


def test_unknown_track_uses_hymo_fallback(env, mocker):
    dm, sm, dl_path, lmu_path = env
    from domain.setup import Setup
    mystery = Setup({
        "id": "mystery-1",
        "title": "Mystery",
        "setupCombos": [{"car": {"name": "Ferrari"}, "track": {"name": "Mystery Circuit"}}],
        "hotlapLink": None,
        "lastUpdatedAt": 1,
        "isBundle": False,
    })

    zip_path = dl_path / f"{mystery.safe_track}-{mystery.id}.zip"
    zip_path.write_bytes(b"zip")

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "f.svm").write_bytes(b"x")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)
    sm.install_setup(zip_path, mystery)

    assert (lmu_path / "Mystery Circuit-HYMO").exists()
    assert dm.database.is_track_found("mystery-1") is False
