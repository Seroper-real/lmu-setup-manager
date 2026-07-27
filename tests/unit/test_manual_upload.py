import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


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
    m.get_car_name.return_value = None
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

    upload_manual_setup_to_dropbox(dropbox_client, original, setup, "HYMO")

    package_path = dl_path / setup.remote_filename
    assert not package_path.exists()
    assert original.exists()  # only the repackaged temp zip is cleaned up, never the user's original
