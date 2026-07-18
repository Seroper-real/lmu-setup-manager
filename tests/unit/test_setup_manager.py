import pytest
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def lmu_base(tmp_path):
    d = tmp_path / "lmu"
    d.mkdir()
    return d


@pytest.fixture
def mock_track_manager():
    m = MagicMock()
    m.get_track_folder_name.return_value = "Spa"
    return m


@pytest.fixture
def sm(in_memory_db, mock_track_manager, lmu_base, mocker):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.setup_manager.OVERWRITE", True)
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", False)
    mocker.patch("processing.setup_manager.SETUP_FILE_EXTENSIONS", {".svm"})
    from processing.setup_manager import SetupManager
    return SetupManager(
        database=in_memory_db,
        track_manager=mock_track_manager,
        lmu_setups_base_path=lmu_base,
        overwrite=True,
        already_installed=set(),
    )


def test_calculate_dir_known_track(sm, lmu_base):
    path, found, matched_track_id = sm._calculate_setup_installation_dir("Spa-Francorchamps")
    assert found is True
    assert path == lmu_base / "Spa"
    assert matched_track_id == "Spa"


def test_calculate_dir_unknown_track(sm, lmu_base):
    sm.track_manager.get_track_folder_name.return_value = None
    path, found, matched_track_id = sm._calculate_setup_installation_dir("Mystery Circuit")
    assert found is False
    assert "HYMO" in path.name
    assert matched_track_id is None


def test_find_files_recursive(sm, tmp_path):
    (tmp_path / "a.svm").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.svm").write_bytes(b"x")
    result = {f.name for f in sm._find_files_recursive(tmp_path, {".svm"})}
    assert "a.svm" in result
    assert "c.svm" in result
    assert "b.txt" not in result


def test_copy_to_lmu_copies_files(sm, tmp_path, lmu_base):
    src = tmp_path / "extracted"
    src.mkdir()
    (src / "setup.svm").write_bytes(b"data")
    dest = lmu_base / "Spa"
    sm._copy_file_to_lmu(src, dest)
    assert (dest / "setup.svm").exists()


def test_copy_to_lmu_no_overwrite(sm, tmp_path, lmu_base):
    sm.overwrite = False
    src = tmp_path / "extracted"
    src.mkdir()
    (src / "setup.svm").write_bytes(b"new")
    dest = lmu_base / "Spa"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "setup.svm").write_bytes(b"old")
    sm._copy_file_to_lmu(src, dest)
    assert (dest / "setup.svm").read_bytes() == b"old"


def test_cleanup_temp_removes_extraction_dir(sm, tmp_path):
    ext = tmp_path / "extracted"
    ext.mkdir()
    dl = tmp_path / "file.zip"
    dl.write_bytes(b"zip")
    sm._cleanup_temp(dl, ext, installed=True)
    assert not ext.exists()
    assert dl.exists()  # CLEAN_DOWNLOAD=False


def test_cleanup_temp_deletes_zip_when_enabled(sm, tmp_path, mocker):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", True)
    ext = tmp_path / "extracted"
    ext.mkdir()
    dl = tmp_path / "file.zip"
    dl.write_bytes(b"zip")
    sm._cleanup_temp(dl, ext, installed=True)
    assert not dl.exists()


def test_cleanup_old_removes_stale_files(sm, tmp_path):
    install_dir = tmp_path / "Spa"
    install_dir.mkdir()
    (install_dir / "old.svm").write_bytes(b"old")
    (install_dir / "new.svm").write_bytes(b"new")
    sm._cleanup_old(["old.svm", "new.svm"], install_dir, [Path("new.svm")])
    assert not (install_dir / "old.svm").exists()
    assert (install_dir / "new.svm").exists()


def test_unzip_recursive_raises_if_missing(sm, tmp_path):
    with pytest.raises(FileNotFoundError):
        sm._unzip_recursive(tmp_path / "missing.zip", tmp_path / "out")


def test_install_setup_full_flow(sm, sample_setup, tmp_path, lmu_base, mocker):
    dl_path = tmp_path / "downloads"
    dl_path.mkdir()
    mocker.patch("processing.setup_manager.DOWNLOAD_PATH", dl_path)

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "car_spa.svm").write_bytes(b"setup bytes")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    zip_path = dl_path / f"{sample_setup.safe_track}-{sample_setup.id}.zip"
    zip_path.write_bytes(b"fake zip")

    sm.install_setup(zip_path, sample_setup)

    assert (lmu_base / "Spa" / "car_spa.svm").exists()
    assert sm.database.is_setup_installed_last_version(sample_setup) is True


def test_delete_setup_removes_files_and_db_row(sm, in_memory_db, lmu_base, sample_setup):
    install_dir = lmu_base / "Spa"
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "car_spa.svm").write_bytes(b"x")
    in_memory_db.add_installed_setup(sample_setup, [install_dir / "car_spa.svm"], True, install_dir)

    deleted = sm.delete_setup(sample_setup.id)

    assert deleted is True
    assert not (install_dir / "car_spa.svm").exists()
    assert in_memory_db.fetch_installed_setup(sample_setup.id) is None


def test_delete_setup_ignores_a_file_already_missing_on_disk(sm, in_memory_db, lmu_base, sample_setup):
    install_dir = lmu_base / "Spa"
    in_memory_db.add_installed_setup(sample_setup, [install_dir / "car_spa.svm"], True, install_dir)

    deleted = sm.delete_setup(sample_setup.id)

    assert deleted is True
    assert in_memory_db.fetch_installed_setup(sample_setup.id) is None


def test_delete_setup_returns_false_for_an_unknown_id(sm):
    assert sm.delete_setup("ghost") is False


def test_setup_manager_creates_a_missing_lmu_base_path_on_init(in_memory_db, mock_track_manager, tmp_path, mocker):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.setup_manager.OVERWRITE", True)
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", False)
    from processing.setup_manager import SetupManager

    missing = tmp_path / "not-yet-created" / "Settings"
    assert not missing.exists()

    SetupManager(database=in_memory_db, track_manager=mock_track_manager, lmu_setups_base_path=missing)

    assert missing.is_dir()


def test_update_tracks_not_found_relocates_setup(sm, in_memory_db, lmu_base, mocker):
    old_dir = lmu_base / "Spa-Francorchamps-HYMO"
    old_dir.mkdir(parents=True)
    (old_dir / "setup.svm").write_bytes(b"x")

    from domain.setup import Setup
    s = Setup({
        "id": "relocate-me",
        "title": "T",
        "setupCombos": [{"car": {"name": "Ferrari"}, "track": {"name": "Spa-Francorchamps"}}],
        "hotlapLink": None,
        "lastUpdatedAt": 1,
        "isBundle": False,
    })
    in_memory_db.add_installed_setup(s, [old_dir / "setup.svm"], False, old_dir)

    sm.track_manager.get_track_folder_name.return_value = "Spa"
    sm.update_tracks_not_found()

    assert (lmu_base / "Spa" / "setup.svm").exists()
    assert in_memory_db.is_track_found("relocate-me") is True
    relocated = in_memory_db.fetch_all_installed_setups()[0]
    assert relocated.matched_track_id == "Spa"
