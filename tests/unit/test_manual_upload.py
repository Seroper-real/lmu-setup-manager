import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_guess_car_track_from_filename_searches_car_and_track_matchers():
    from processing.manual_upload import guess_car_track_from_filename

    car_manager = MagicMock()
    car_manager.get_car_name.return_value = "Ferrari 499P"
    track_manager = MagicMock()
    track_manager.get_track_folder_name.return_value = "Sebring"

    car, track = guess_car_track_from_filename("GO-FERRARI-499P-SEBRING.zip", car_manager, track_manager)

    assert (car, track) == ("Ferrari 499P", "Sebring")
    # Extension stripped, raw stem handed to both matchers unmodified - the
    # patterns themselves are substring regexes, so no bespoke splitting of
    # car vs track is attempted.
    car_manager.get_car_name.assert_called_once_with("GO-FERRARI-499P-SEBRING")
    track_manager.get_track_folder_name.assert_called_once_with("GO-FERRARI-499P-SEBRING")


def test_guess_car_track_from_filename_against_real_mapping_json():
    """End-to-end with the actual bundled mapping.json, matching the exact
    naming convention this feature exists for."""
    from processing.car_manager import CarManager
    from processing.manual_upload import guess_car_track_from_filename
    from processing.track_manager import TrackManager

    car, track = guess_car_track_from_filename(
        "GO-FERRARI-499P-SEBRING.zip", CarManager(), TrackManager()
    )

    assert (car, track) == ("Ferrari 499P", "Sebring")


def test_guess_car_track_from_filename_returns_none_when_unrecognized():
    from processing.manual_upload import guess_car_track_from_filename

    car_manager = MagicMock()
    car_manager.get_car_name.return_value = None
    track_manager = MagicMock()
    track_manager.get_track_folder_name.return_value = None

    assert guess_car_track_from_filename("setup1.zip", car_manager, track_manager) == (None, None)


def test_build_manual_setup_shapes_a_synthetic_setup():
    from processing.manual_upload import build_manual_setup

    setup = build_manual_setup("Spa", "Porsche 963")

    assert setup.track == "Spa"
    assert setup.car == "Porsche 963"
    assert setup.hotlap_link is None
    assert setup.is_bundle is False
    assert setup.id


def test_build_manual_setup_gives_each_call_a_distinct_id():
    from processing.manual_upload import build_manual_setup

    assert build_manual_setup("Spa", "Porsche 963").id != build_manual_setup("Spa", "Porsche 963").id


def test_build_manual_setup_keeps_safe_track_and_car_matching_mapping_json_name_exactly():
    """track/car are already the exact mapping.json `name` values (the Upload
    tab's dropdowns are built from mapping.json) - Setup's default
    sanitize_identity would mangle a hyphen or slash in one of those names, so
    build_manual_setup must bypass it and use the given strings as-is."""
    from processing.manual_upload import build_manual_setup

    setup = build_manual_setup("Imola", "Cadillac V-Series.R")

    assert setup.safe_track == "Imola"
    assert setup.safe_car == "Cadillac V-Series.R"


# ----- install_manual_setup_locally ------------------------------------------


@pytest.fixture
def dl_path(tmp_path, mocker):
    p = tmp_path / "downloads"
    p.mkdir()
    mocker.patch("processing.manual_upload.DOWNLOAD_PATH", p)
    return p


@pytest.fixture
def mock_track_manager():
    m = MagicMock()
    m.get_track_folder_name.return_value = "Spa"
    m.get_official_track_name.return_value = None
    return m


@pytest.fixture
def mock_car_manager():
    m = MagicMock()
    # Matched by default (matches every build_manual_setup(..., "Porsche 963")
    # call in this module) - install_setup() now skips entirely on an
    # unmatched car/track rather than installing under a placeholder name.
    m.get_car_name.return_value = "Porsche 963"
    return m


@pytest.fixture
def sm(in_memory_db, mock_track_manager, mock_car_manager, tmp_path, mocker):
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.setup_manager.OVERWRITE", True)
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", False)
    from processing.setup_manager import SetupManager
    return SetupManager(
        database=in_memory_db,
        track_manager=mock_track_manager,
        car_manager=mock_car_manager,
        lmu_setups_base_path=tmp_path / "lmu",
        overwrite=True,
    )


def test_install_manual_setup_locally_stages_a_copy_and_never_touches_the_original(sm, dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, install_manual_setup_locally

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"data")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "my-original.zip"
    original.write_bytes(b"the user's own file")

    setup = build_manual_setup("Spa", "Porsche 963")
    install_manual_setup_locally(sm, original, setup, "HYMO")

    # install_setup() takes ownership of (and may delete) whatever path it's
    # handed - the original must never be that path.
    assert original.exists()
    assert original.read_bytes() == b"the user's own file"
    assert (sm.lmu_setups_base_path / "Spa" / "setup.svm").exists()
    row = sm.database.fetch_installed_setup(setup.id)
    assert row.setup_type == "HYMO"


def test_install_manual_setup_locally_uses_go_extensions_for_go_type(sm, dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, install_manual_setup_locally

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"x")
        (Path(outdir) / "telemetry.ld").write_bytes(b"x")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "go-setup.zip"
    original.write_bytes(b"zip")

    setup = build_manual_setup("Spa", "Porsche 963")
    install_manual_setup_locally(sm, original, setup, "GO")

    assert (sm.lmu_setups_base_path / "Spa" / "setup.svm").exists()
    assert (sm.lmu_setups_base_path / "Spa" / "telemetry.ld").exists()
    row = sm.database.fetch_installed_setup(setup.id)
    assert row.setup_type == "GO"


def test_install_manual_setup_locally_populates_sha256(sm, dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, install_manual_setup_locally

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"data")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "my-original.zip"
    original.write_bytes(b"the user's own file")

    setup = build_manual_setup("Spa", "Porsche 963")
    install_manual_setup_locally(sm, original, setup, "HYMO")

    row = sm.database.fetch_installed_setup(setup.id)
    assert row.sha256 is not None


def test_install_manual_setup_locally_updates_a_previous_manual_upload_for_the_same_identity(
    sm, dl_path, tmp_path, mocker
):
    """A second manual upload for the same car/track/type must reuse the
    first row's id (so it upserts in place) instead of installing alongside
    it as an unrelated, brand-new setup."""
    from processing.manual_upload import build_manual_setup, install_manual_setup_locally

    def fake_extract_v1(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "quali_v1.svm").write_bytes(b"v1")

    def fake_extract_v2(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "quali_v2.svm").write_bytes(b"v2")

    original = tmp_path / "my-setup.zip"
    original.write_bytes(b"zip")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract_v1)
    first = build_manual_setup("Spa", "Porsche 963")
    install_manual_setup_locally(sm, original, first, "HYMO")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract_v2)
    second = build_manual_setup("Spa", "Porsche 963")
    assert second.id != first.id
    install_manual_setup_locally(sm, original, second, "HYMO")

    assert second.id == first.id, "the second upload must be reassigned the first's id"
    assert sm.database.fetch_installed_setup(first.id) is not None
    cur = sm.database.conn.execute(
        "SELECT COUNT(*) FROM installed_setups WHERE car='Porsche 963' AND track='Spa' AND setup_type='HYMO'"
    )
    assert cur.fetchone()[0] == 1


def test_install_manual_setup_locally_keeps_hymo_and_go_as_separate_rows(sm, dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, install_manual_setup_locally

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"data")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)
    original = tmp_path / "my-setup.zip"
    original.write_bytes(b"zip")

    hymo_setup = build_manual_setup("Spa", "Porsche 963")
    install_manual_setup_locally(sm, original, hymo_setup, "HYMO")

    go_setup = build_manual_setup("Spa", "Porsche 963")
    install_manual_setup_locally(sm, original, go_setup, "GO")

    assert go_setup.id != hymo_setup.id
    assert sm.database.fetch_installed_setup(hymo_setup.id).setup_type == "HYMO"
    assert sm.database.fetch_installed_setup(go_setup.id).setup_type == "GO"


# ----- upload_manual_setup_to_dropbox: GO branch (copy + embedded metadata) --


def _make_go_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def test_upload_manual_setup_to_dropbox_go_uploads_a_copy_with_embedded_metadata(dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", False)

    original = tmp_path / "MySetup.zip"
    _make_go_zip(original, {"GO 1.0 Q.svm": b"svm data"})
    original_bytes = original.read_bytes()
    setup = build_manual_setup("Spa", "Porsche 963")
    dropbox_client = MagicMock()
    dropbox_client.find_existing_setup.return_value = None

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "GO")

    dropbox_client.upload.assert_called_once()
    uploaded_path, remote_relative_path = dropbox_client.upload.call_args[0]
    assert remote_relative_path == f"{setup.safe_car}/{setup.safe_track}/{setup.go_filename}"
    assert Path(uploaded_path) != original

    # The original file is a plain copy source, never mutated or deleted.
    assert original.exists()
    assert original.read_bytes() == original_bytes

    with zipfile.ZipFile(uploaded_path) as zf:
        names = zf.namelist()
        assert "GO 1.0 Q.svm" in names
        assert ".metadata.json" in names
        metadata = json.loads(zf.read(".metadata.json"))
        assert metadata["id"] == setup.id


def test_upload_manual_setup_to_dropbox_go_names_the_archive_from_id_and_date_regardless_of_original_name(
    dl_path, tmp_path, mocker
):
    """The uploaded filename must carry id/date info the same way a HYMO
    archive's remote_filename does (see Setup.go_filename) - GO- branded
    instead of HYMO- so it's still recognized as a GO Setups archive -
    regardless of what the user's original file was called."""
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", False)

    original = tmp_path / "whatever-the-user-called-it.zip"
    _make_go_zip(original, {"GO 1.0 Q.svm": b"svm data"})
    setup = build_manual_setup("Spa", "Porsche 963")
    dropbox_client = MagicMock()
    dropbox_client.find_existing_setup.return_value = None

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "GO")

    _, remote_relative_path = dropbox_client.upload.call_args[0]
    assert remote_relative_path == f"{setup.safe_car}/{setup.safe_track}/{setup.go_filename}"
    assert setup.go_filename.startswith("GO-")
    assert setup.id in setup.go_filename
    assert str(setup.last_updated) in setup.go_filename


def test_upload_manual_setup_to_dropbox_go_cleans_up_the_staged_copy_when_clean_download_is_on(dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", True)

    original = tmp_path / "MySetup.zip"
    _make_go_zip(original, {"GO 1.0 Q.svm": b"svm data"})
    setup = build_manual_setup("Spa", "Porsche 963")
    dropbox_client = MagicMock()
    dropbox_client.find_existing_setup.return_value = None

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "GO")

    uploaded_path, _ = dropbox_client.upload.call_args[0]
    assert not Path(uploaded_path).exists()
    assert original.exists()


# ----- upload_manual_setup_to_dropbox: HYMO branch (repackaged + metadata) ---


def test_upload_manual_setup_to_dropbox_hymo_repackages_with_embedded_metadata(dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.manual_upload.SETUP_FILE_EXTENSIONS", {".svm"})

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"setup data")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "my-setup.zip"
    original.write_bytes(b"zip")
    setup = build_manual_setup("Spa", "Porsche 963")
    dropbox_client = MagicMock()
    dropbox_client.find_existing_setup.return_value = None

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "HYMO")

    dropbox_client.upload.assert_called_once()
    uploaded_package_path, remote_relative_path = dropbox_client.upload.call_args[0]
    assert remote_relative_path == setup.remote_relative_path
    assert Path(uploaded_package_path).name.startswith("HYMO-")
    with zipfile.ZipFile(uploaded_package_path) as zf:
        names = zf.namelist()
        assert "setup.svm" in names
        assert ".metadata.json" in names
        metadata = json.loads(zf.read(".metadata.json"))
        assert metadata["id"] == setup.id
    assert original.exists()


def test_upload_manual_setup_to_dropbox_hymo_raises_when_no_recognized_files(dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.SETUP_FILE_EXTENSIONS", {".svm"})

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "readme.txt").write_bytes(b"not a setup")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "my-setup.zip"
    original.write_bytes(b"zip")
    setup = build_manual_setup("Spa", "Porsche 963")
    dropbox_client = MagicMock()
    dropbox_client.find_existing_setup.return_value = None

    with pytest.raises(ValueError):
        upload_manual_setup_to_dropbox(dropbox_client, original, setup, "HYMO")

    dropbox_client.upload.assert_not_called()


def test_upload_manual_setup_to_dropbox_hymo_cleans_up_the_package_when_clean_download_is_on(dl_path, tmp_path, mocker):
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", True)
    mocker.patch("processing.manual_upload.SETUP_FILE_EXTENSIONS", {".svm"})

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"setup data")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "my-setup.zip"
    original.write_bytes(b"zip")
    setup = build_manual_setup("Spa", "Porsche 963")
    dropbox_client = MagicMock()
    dropbox_client.find_existing_setup.return_value = None

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "HYMO")

    package_path = dl_path / setup.remote_filename
    assert not package_path.exists()
    assert original.exists()  # only the repackaged temp zip is cleaned up, never the user's original


# ----- upload_manual_setup_to_dropbox: update detection (same car/track/type) -


def test_upload_manual_setup_to_dropbox_hymo_reuses_the_existing_id_and_deletes_the_previous_version(
    dl_path, tmp_path, mocker
):
    """A second manual HYMO upload for the same car/track is an update: the
    new package must carry the *same* id as the one already on the share
    (only the date changes), and the stale zip must be deleted once the new
    one lands - same identity SlaveManager._process keys off of."""
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox
    from domain.setup import RemoteSetup

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.manual_upload.SETUP_FILE_EXTENSIONS", {".svm"})

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"setup data v2")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "my-setup.zip"
    original.write_bytes(b"zip")
    setup = build_manual_setup("Spa", "Porsche 963")

    dropbox_client = MagicMock()
    existing = RemoteSetup(
        name="HYMO-Spa_Porsche_963_old-id_1000.zip", path_lower="/car/track/HYMO-Spa_Porsche_963_old-id_1000.zip",
        setup_id="old-id", ts=1000,
    )
    dropbox_client.find_existing_setup.return_value = existing

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "HYMO")

    assert setup.id == "old-id"
    _, remote_relative_path = dropbox_client.upload.call_args[0]
    assert remote_relative_path == setup.remote_relative_path
    assert "old-id" in remote_relative_path
    dropbox_client.delete.assert_called_once_with(existing.path_lower)


def test_upload_manual_setup_to_dropbox_hymo_does_not_delete_when_nothing_previously_published(
    dl_path, tmp_path, mocker
):
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", False)
    mocker.patch("processing.manual_upload.SETUP_FILE_EXTENSIONS", {".svm"})

    def fake_extract(archive, outdir, verbosity):
        Path(outdir).mkdir(parents=True, exist_ok=True)
        (Path(outdir) / "setup.svm").write_bytes(b"setup data")

    mocker.patch("core.archive.patoolib.extract_archive", side_effect=fake_extract)

    original = tmp_path / "my-setup.zip"
    original.write_bytes(b"zip")
    setup = build_manual_setup("Spa", "Porsche 963")
    dropbox_client = MagicMock()
    dropbox_client.find_existing_setup.return_value = None

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "HYMO")

    dropbox_client.delete.assert_not_called()


def test_upload_manual_setup_to_dropbox_go_deletes_the_previous_version_on_update(dl_path, tmp_path, mocker):
    """GO Setups have no stable id (see domain/go_setup.py) - the update check
    is purely "was there already a GO archive in this car/track folder"."""
    from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

    mocker.patch("processing.manual_upload.CLEAN_DOWNLOAD", False)

    original = tmp_path / "MySetup.zip"
    _make_go_zip(original, {"GO 1.0 Q.svm": b"svm data v2"})
    setup = build_manual_setup("Spa", "Porsche 963")

    dropbox_client = MagicMock()
    existing = MagicMock()
    existing.name = "GO-Spa_Porsche_963_old-id_1000.zip"
    existing.path_lower = "/car/track/GO-Spa_Porsche_963_old-id_1000.zip"
    dropbox_client.find_existing_setup.return_value = existing

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "GO")

    dropbox_client.delete.assert_called_once_with(existing.path_lower)
