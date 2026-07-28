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
    # None: install_setup() falls back to track_folder_name as the official
    # name (get_official_track_name(...) or track_folder_name), same as a
    # real TrackManager whose custom layer has no distinct `name`.
    m.get_official_track_name.return_value = None
    return m


@pytest.fixture
def mock_car_manager():
    m = MagicMock()
    # Matched by default (matches sample_setup's car, see conftest.py) - a
    # car/track that fails to resolve is no longer installed at all (see the
    # dedicated "unmatched" tests below), so most of this module's tests need
    # both managers to report a match to exercise what they're actually about.
    m.get_car_name.return_value = "Porsche 963"
    return m


@pytest.fixture
def sm(in_memory_db, mock_track_manager, mock_car_manager, lmu_base, mocker):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.setup_manager.OVERWRITE", True)
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", False)
    mocker.patch("processing.setup_manager.SETUP_FILE_EXTENSIONS", {".svm"})
    from processing.setup_manager import SetupManager
    return SetupManager(
        database=in_memory_db,
        track_manager=mock_track_manager,
        car_manager=mock_car_manager,
        lmu_setups_base_path=lmu_base,
        overwrite=True,
        already_installed=set(),
    )


def test_calculate_dir_known_track(sm, lmu_base):
    path = sm._calculate_setup_installation_dir("Spa-Francorchamps")
    assert path == lmu_base / "Spa"


def test_calculate_dir_unknown_track_returns_none(sm):
    sm.track_manager.get_track_folder_name.return_value = None
    assert sm._calculate_setup_installation_dir("Mystery Circuit") is None


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


@pytest.mark.parametrize("extensions, expected_names", [
    # extensions omitted (falls back to SETUP_FILE_EXTENSIONS, {".svm"} per the
    # `sm` fixture) behaves identically to passing extensions=None explicitly -
    # both hit the same `exts = extensions if extensions is not None else ...` branch.
    pytest.param(None, {"setup.svm"}, id="defaults_to_setup_file_extensions"),
    pytest.param({".ld", ".ldx"}, {"telemetry.ld", "telemetry.ldx"}, id="explicit_override"),
])
def test_copy_to_lmu_extensions_filter(sm, tmp_path, lmu_base, extensions, expected_names):
    src = tmp_path / "extracted"
    src.mkdir()
    (src / "setup.svm").write_bytes(b"x")
    (src / "telemetry.ld").write_bytes(b"x")
    (src / "telemetry.ldx").write_bytes(b"x")
    dest = lmu_base / "Spa"

    copied = sm._copy_file_to_lmu(src, dest, extensions=extensions)

    assert {f.name for f in copied} == expected_names
    assert {f.name for f in dest.iterdir()} == expected_names


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


@pytest.mark.parametrize("clean_download, zip_should_survive", [
    pytest.param(False, True, id="clean_download_off_keeps_zip"),
    pytest.param(True, False, id="clean_download_on_deletes_zip"),
])
def test_cleanup_temp_respects_clean_download_flag(sm, tmp_path, mocker, clean_download, zip_should_survive):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", clean_download)
    ext = tmp_path / "extracted"
    ext.mkdir()
    dl = tmp_path / "file.zip"
    dl.write_bytes(b"zip")

    sm._cleanup_temp(dl, ext, installed=True)

    assert not ext.exists()  # extraction dir is always removed
    assert dl.exists() == zip_should_survive


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


@pytest.fixture
def install_setup_env(tmp_path, mocker):
    """Common install_setup() plumbing shared by every test below: a writable
    download dir, a real-archive-extractor stand-in that drops the given files
    into outdir, and the source zip install_setup() expects to find on disk."""
    dl_path = tmp_path / "downloads"
    dl_path.mkdir()
    mocker.patch("processing.setup_manager.DOWNLOAD_PATH", dl_path)

    def _prepare(files: dict[str, bytes], zip_name: str = "fake.zip") -> Path:
        def fake_extract(archive, outdir, verbosity):
            Path(outdir).mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (Path(outdir) / name).write_bytes(content)

        mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)
        zip_path = dl_path / zip_name
        zip_path.write_bytes(b"fake zip")
        return zip_path

    return _prepare


def test_install_setup_full_flow(sm, sample_setup, lmu_base, install_setup_env):
    zip_path = install_setup_env(
        {"car_spa.svm": b"setup bytes"},
        zip_name=f"{sample_setup.safe_track}-{sample_setup.id}.zip",
    )

    sm.install_setup(zip_path, sample_setup)

    assert (lmu_base / "Spa" / "car_spa.svm").exists()
    assert sm.database.is_setup_installed_last_version(sample_setup) is True


@pytest.mark.parametrize("install_kwargs, expected_setup_type, expected_sha256", [
    pytest.param({}, "HYMO", None, id="defaults_to_hymo"),
    pytest.param(
        {"setup_type": "GO", "sha256": "abc123"}, "GO", "abc123",
        id="threads_sha256_and_setup_type",
    ),
])
def test_install_setup_records_setup_type_and_sha256_in_db(
    sm, sample_setup, install_setup_env, install_kwargs, expected_setup_type, expected_sha256,
):
    zip_path = install_setup_env({"car_spa.svm": b"setup bytes"})

    sm.install_setup(zip_path, sample_setup, **install_kwargs)

    row = sm.database.fetch_installed_setup(sample_setup.id)
    assert row.setup_type == expected_setup_type
    assert row.sha256 == expected_sha256


@pytest.mark.parametrize("setup_type, extra_kwargs", [
    pytest.param("GO", {"setup_type": "GO"}, id="go"),
    # HYMO is the default: no setup_type kwarg passed, same as a real HYMO install.
    pytest.param("HYMO", {}, id="hymo"),
])
def test_install_setup_leaves_stale_files_when_delete_previous_version_is_off(
    sm, sample_setup, lmu_base, install_setup_env, setup_type, extra_kwargs,
):
    # DELETE_PREVIOUS_VERSION must be respected identically regardless of
    # setup_type - no hardcoded per-type cleanup special-case.
    # DELETE_PREVIOUS_VERSION is already patched False by the `sm` fixture.
    install_dir = lmu_base / "Spa"
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "stale.svm").write_bytes(b"stale")
    sm.database.add_installed_setup(sample_setup, [install_dir / "stale.svm"], True, install_dir, setup_type=setup_type)

    zip_path = install_setup_env({"fresh.svm": b"fresh"})

    sm.install_setup(zip_path, sample_setup, **extra_kwargs)

    assert (install_dir / "stale.svm").exists()
    assert (install_dir / "fresh.svm").exists()


# --- install_setup: unmatched car/track is ignored, not installed ----------


@pytest.mark.parametrize("break_track, break_car", [
    pytest.param(True, False, id="track_unmatched"),
    pytest.param(False, True, id="car_unmatched"),
    pytest.param(True, True, id="both_unmatched"),
])
def test_install_setup_skips_when_unmatched(sm, sample_setup, lmu_base, install_setup_env, break_track, break_car):
    if break_track:
        sm.track_manager.get_track_folder_name.return_value = None
    if break_car:
        sm.car_manager.get_car_name.return_value = None
    zip_path = install_setup_env({"car_spa.svm": b"setup bytes"})

    result = sm.install_setup(zip_path, sample_setup)

    assert result is False
    assert not (lmu_base / "Spa" / "car_spa.svm").exists()
    assert sm.database.fetch_installed_setup(sample_setup.id) is None


def test_install_setup_matched_returns_true(sm, sample_setup, install_setup_env):
    zip_path = install_setup_env({"car_spa.svm": b"setup bytes"})
    assert sm.install_setup(zip_path, sample_setup) is True


def test_install_setup_unmatched_deletes_download_when_clean_download_enabled(
    sm, sample_setup, install_setup_env, mocker,
):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", True)
    sm.car_manager.get_car_name.return_value = None
    zip_path = install_setup_env({"car_spa.svm": b"setup bytes"})

    assert sm.install_setup(zip_path, sample_setup) is False
    assert not zip_path.exists()


def test_install_setup_unmatched_keeps_download_when_clean_download_disabled(sm, sample_setup, install_setup_env):
    # CLEAN_DOWNLOAD is already patched False by the `sm` fixture.
    sm.car_manager.get_car_name.return_value = None
    zip_path = install_setup_env({"car_spa.svm": b"setup bytes"})

    assert sm.install_setup(zip_path, sample_setup) is False
    assert zip_path.exists()


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


def test_setup_manager_creates_a_missing_lmu_base_path_on_init(in_memory_db, mock_track_manager, mock_car_manager, tmp_path, mocker):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.setup_manager.OVERWRITE", True)
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", False)
    from processing.setup_manager import SetupManager

    missing = tmp_path / "not-yet-created" / "Settings"
    assert not missing.exists()

    SetupManager(database=in_memory_db, track_manager=mock_track_manager, car_manager=mock_car_manager, lmu_setups_base_path=missing)

    assert missing.is_dir()


