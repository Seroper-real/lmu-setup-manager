"""GO Setups: manually-uploaded archives recognized purely by their <Car>/<Track>
Dropbox folder, installed by SLAVE alongside this tool's own TrackTitan setups.

Identity is the <Car>/<Track> folder alone (never the filename); "already
installed" is decided purely by a SHA-256 checksum of the downloaded archive.
"""
import zipfile

import pytest

from sandbox_harness import make_setup

CAR = "Oreca 07"
TRACK = "Imola"
ZIP_NAME = "GO-ORECA-07-ELMS-IMOLA.zip"


@pytest.fixture(autouse=True)
def _tracks(sandbox):
    sandbox.set_tracks([("imola", "Imola")])


def _row_for_track(db, track):
    """The GO row for `track` (setup_type-scoped: every test in this file now
    also has a HYMO precondition row for the same track, per the has-a-
    matching-HYMO-setup gate GO installs require)."""
    matches = [r for r in db.fetch_all_installed_setups() if r.track == track and r.setup_type == "GO"]
    assert len(matches) == 1, f"expected exactly one GO row for track {track!r}, found {len(matches)}"
    return matches[0]


def _install_hymo_precondition(sandbox, in_memory_db, car=CAR, track=TRACK, setup_id="hymo-precondition-uuid"):
    """Publish+install a HYMO setup for car/track - the GO gate
    (SetupDb.has_installed_hymo_setup) requires one to already exist before a
    GO archive for that same folder is trusted."""
    sandbox.write_catalog([make_setup(setup_id, track, car=car)])
    sandbox.add_archive(setup_id, {"tt_quali.svm": "tt"})
    sandbox.run_master()
    sandbox.run_slave(in_memory_db)


def test_go_archive_installs_svm_and_telemetry_with_setup_type_and_sha256(sandbox, in_memory_db):
    _install_hymo_precondition(sandbox, in_memory_db)
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {
        "GO 1.0 Q.svm": "svm-v1",
        "GO 1.0 Q MOTEC.ld": "ld-v1",
        "GO 1.0 Q MOTEC.ldx": "ldx-v1",
    })

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {
        "Imola/tt_quali.svm",
        "Imola/GO 1.0 Q.svm", "Imola/GO 1.0 Q MOTEC.ld", "Imola/GO 1.0 Q MOTEC.ldx",
    }
    row = _row_for_track(in_memory_db, TRACK)
    assert row.setup_type == "GO"
    assert row.car == CAR
    assert row.sha256 is not None


def test_content_change_under_the_same_filename_replaces_stale_files(sandbox, in_memory_db):
    _install_hymo_precondition(sandbox, in_memory_db)
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 1.0 Q.svm": "v1"})
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Imola/tt_quali.svm", "Imola/GO 1.0 Q.svm"}
    setup_id_v1 = _row_for_track(in_memory_db, TRACK).setup_id

    # Same Dropbox path, totally different internal filenames - no version
    # signal anywhere except the content itself.
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 2.0 Q Esport.svm": "v2"})
    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Imola/tt_quali.svm", "Imola/GO 2.0 Q Esport.svm"}
    row = _row_for_track(in_memory_db, TRACK)
    assert row.setup_id == setup_id_v1


def test_unchanged_archive_is_not_reinstalled_on_a_second_run(sandbox, in_memory_db, mocker):
    _install_hymo_precondition(sandbox, in_memory_db)
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 1.0 Q.svm": "v1"})
    sandbox.run_slave(in_memory_db)

    from processing.setup_manager import SetupManager
    install_spy = mocker.spy(SetupManager, "install_setup")

    sandbox.run_slave(in_memory_db)

    install_spy.assert_not_called()
    assert sandbox.installed_files() == {"Imola/tt_quali.svm", "Imola/GO 1.0 Q.svm"}


def test_renaming_the_zip_in_place_with_unchanged_content_is_not_reinstalled(sandbox, in_memory_db, mocker):
    _install_hymo_precondition(sandbox, in_memory_db)
    original = sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 1.0 Q.svm": "same content"})
    sandbox.run_slave(in_memory_db)
    setup_id_before = _row_for_track(in_memory_db, TRACK).setup_id

    # A real rename keeps the bytes identical - re-creating the zip from
    # scratch would not (zip entries embed a creation timestamp), so copy the
    # exact bytes under the new name instead of calling add_go_zip() again.
    renamed = sandbox.share / CAR / TRACK / "GO-Renamed.zip"
    renamed.write_bytes(original.read_bytes())
    original.unlink()

    from processing.setup_manager import SetupManager
    install_spy = mocker.spy(SetupManager, "install_setup")

    sandbox.run_slave(in_memory_db)

    install_spy.assert_not_called()
    row = _row_for_track(in_memory_db, TRACK)
    assert row.setup_id == setup_id_before
    assert sandbox.installed_files() == {"Imola/tt_quali.svm", "Imola/GO 1.0 Q.svm"}


def test_renaming_and_changing_content_still_updates_the_same_slot(sandbox, in_memory_db):
    _install_hymo_precondition(sandbox, in_memory_db)
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 1.0 Q.svm": "v1"})
    sandbox.run_slave(in_memory_db)
    setup_id_before = _row_for_track(in_memory_db, TRACK).setup_id

    (sandbox.share / CAR / TRACK / ZIP_NAME).unlink()
    sandbox.add_go_zip(CAR, TRACK, "GO-Renamed-v2.zip", {"GO 2.0 Q Esport.svm": "v2"})
    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Imola/tt_quali.svm", "Imola/GO 2.0 Q Esport.svm"}
    row = _row_for_track(in_memory_db, TRACK)
    assert row.setup_id == setup_id_before


def test_tracktitan_setup_and_go_archive_for_the_same_track_share_the_lmu_folder(sandbox, in_memory_db):
    # Two different cars' HYMO setups, both installed for the same track
    # (Porsche 963 unrelated to the GO archive below, Oreca 07 the one it
    # attaches to - the GO gate requires a HYMO row for its exact car+track).
    porsche_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    oreca_id = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
    sandbox.write_catalog([
        make_setup(porsche_id, TRACK, car="Porsche 963"),
        make_setup(oreca_id, TRACK, car=CAR),
    ])
    sandbox.add_archive(porsche_id, {"tt_quali.svm": "tt"})
    sandbox.add_archive(oreca_id, {"oreca_quali.svm": "oreca-tt"})
    sandbox.run_master()
    sandbox.run_slave(in_memory_db)

    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"go_quali.svm": "go"})
    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {
        "Imola/tt_quali.svm", "Imola/oreca_quali.svm", "Imola/go_quali.svm",
    }


def test_go_identity_stays_stable_when_a_hymo_setup_shares_the_same_car_and_track(sandbox, in_memory_db):
    """A TrackTitan setup and a GO archive can legitimately target the exact
    same car+track pair - the GO lookup must never latch onto the HYMO row's
    real TrackTitan id (see SetupDb.fetch_installed_go_setup)."""
    tt_setup_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    sandbox.write_catalog([make_setup(tt_setup_id, TRACK, car=CAR)])
    sandbox.add_archive(tt_setup_id, {"tt_quali.svm": "tt"})
    sandbox.run_master()
    sandbox.run_slave(in_memory_db)

    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"go_quali.svm": "go-v1"})
    sandbox.run_slave(in_memory_db)

    go_rows = [r for r in in_memory_db.fetch_all_installed_setups() if r.setup_type == "GO"]
    assert len(go_rows) == 1
    go_setup_id = go_rows[0].setup_id
    assert go_setup_id != tt_setup_id

    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"go_quali_v2.svm": "go-v2"})
    sandbox.run_slave(in_memory_db)

    go_rows_after = [r for r in in_memory_db.fetch_all_installed_setups() if r.setup_type == "GO"]
    assert len(go_rows_after) == 1
    assert go_rows_after[0].setup_id == go_setup_id
    hymo_row = next(r for r in in_memory_db.fetch_all_installed_setups() if r.setup_type == "HYMO")
    assert hymo_row.setup_id == tt_setup_id
    assert sandbox.installed_files() == {"Imola/tt_quali.svm", "Imola/go_quali_v2.svm"}


def test_go_archive_is_skipped_when_no_matching_hymo_setup_exists(sandbox, in_memory_db):
    """The gate: a folder existing on the share is not enough on its own - per
    the documented workflow it should only exist because a HYMO setup for that
    exact car+track was already published there, so this GO archive (no such
    HYMO row) is not trusted and never installed."""
    sandbox.add_go_zip("Ferrari 499P", "Nonexistent Circuit", "GO-Ferrari-Mystery.zip", {"go.svm": "x"})

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == set()
    assert in_memory_db.fetch_all_installed_setups() == []


def test_unmapped_go_track_lands_under_go_fallback_suffix_when_hymo_precondition_exists(sandbox, in_memory_db):
    car, track = "Ferrari 499P", "Nonexistent Circuit"
    _install_hymo_precondition(sandbox, in_memory_db, car=car, track=track, setup_id="hymo-unmapped-uuid")

    sandbox.add_go_zip(car, track, "GO-Ferrari-Mystery.zip", {"go.svm": "x"})
    sandbox.run_slave(in_memory_db)

    assert "Nonexistent Circuit-GO/go.svm" in sandbox.installed_files()
    go_rows = [r for r in in_memory_db.fetch_all_installed_setups() if r.setup_type == "GO"]
    assert len(go_rows) == 1
    assert go_rows[0].track_found is False


def test_stray_zip_at_wrong_depth_is_skipped_and_warned(sandbox, in_memory_db, caplog):
    flat = sandbox.share / "GO-Flat.zip"
    flat.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(flat, "w") as zf:
        zf.writestr("go.svm", "x")

    too_deep = sandbox.share / CAR / TRACK / "extra" / "GO-TooDeep.zip"
    too_deep.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(too_deep, "w") as zf:
        zf.writestr("go.svm", "x")

    with caplog.at_level("WARNING"):
        sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == set()
    assert "GO-Flat.zip" in caplog.text
    assert "GO-TooDeep.zip" in caplog.text


def test_correctly_nested_non_go_zip_is_skipped_and_warned_installs_nothing(sandbox, in_memory_db, caplog):
    stray = sandbox.share / CAR / TRACK / "not-a-go-archive.zip"
    stray.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(stray, "w") as zf:
        zf.writestr("random.txt", "x")

    with caplog.at_level("WARNING"):
        sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == set()


def test_go_zip_is_never_picked_up_by_list_setups(sandbox):
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"go.svm": "x"})

    dbx = sandbox.dropbox()

    assert dbx.list_setups() == []
    assert len(dbx.list_go_setups()) == 1
