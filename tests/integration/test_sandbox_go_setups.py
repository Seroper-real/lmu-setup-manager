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
    # Oreca 07 (this module's own CAR) plus Ferrari 499P, used by a couple of
    # tests below - replaces (not merges with) the harness's default "963"
    # -> "Porsche 963" seed, re-included since one test uses it too.
    sandbox.set_cars([("963", "Porsche 963"), ("oreca", "Oreca 07"), ("499p", "Ferrari 499P")])


def _row_for_track(db, track):
    """The GO row for `track` (setup_type-scoped, since a HYMO row can
    legitimately share the same track)."""
    matches = [r for r in db.fetch_all_installed_setups() if r.track == track and r.setup_type == "GO"]
    assert len(matches) == 1, f"expected exactly one GO row for track {track!r}, found {len(matches)}"
    return matches[0]


def test_go_archive_installs_svm_and_telemetry_with_setup_type_and_sha256(sandbox, in_memory_db):
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {
        "GO 1.0 Q.svm": "svm-v1",
        "GO 1.0 Q MOTEC.ld": "ld-v1",
        "GO 1.0 Q MOTEC.ldx": "ldx-v1",
    })

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {
        "Imola/GO 1.0 Q.svm", "Imola/GO 1.0 Q MOTEC.ld", "Imola/GO 1.0 Q MOTEC.ldx",
    }
    row = _row_for_track(in_memory_db, TRACK)
    assert row.setup_type == "GO"
    assert row.car == CAR
    assert row.sha256 is not None


def test_content_change_under_the_same_filename_replaces_stale_files(sandbox, in_memory_db):
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 1.0 Q.svm": "v1"})
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Imola/GO 1.0 Q.svm"}
    setup_id_v1 = _row_for_track(in_memory_db, TRACK).setup_id

    # Same Dropbox path, totally different internal filenames - no version
    # signal anywhere except the content itself.
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 2.0 Q Esport.svm": "v2"})
    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Imola/GO 2.0 Q Esport.svm"}
    row = _row_for_track(in_memory_db, TRACK)
    assert row.setup_id == setup_id_v1


def test_unchanged_archive_is_not_reinstalled_on_a_second_run(sandbox, in_memory_db, mocker):
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 1.0 Q.svm": "v1"})
    sandbox.run_slave(in_memory_db)

    from processing.setup_manager import SetupManager
    install_spy = mocker.spy(SetupManager, "install_setup")

    sandbox.run_slave(in_memory_db)

    install_spy.assert_not_called()
    assert sandbox.installed_files() == {"Imola/GO 1.0 Q.svm"}


def test_renaming_the_zip_in_place_with_unchanged_content_is_not_reinstalled(sandbox, in_memory_db, mocker):
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
    assert sandbox.installed_files() == {"Imola/GO 1.0 Q.svm"}


def test_renaming_and_changing_content_still_updates_the_same_slot(sandbox, in_memory_db):
    sandbox.add_go_zip(CAR, TRACK, ZIP_NAME, {"GO 1.0 Q.svm": "v1"})
    sandbox.run_slave(in_memory_db)
    setup_id_before = _row_for_track(in_memory_db, TRACK).setup_id

    (sandbox.share / CAR / TRACK / ZIP_NAME).unlink()
    sandbox.add_go_zip(CAR, TRACK, "GO-Renamed-v2.zip", {"GO 2.0 Q Esport.svm": "v2"})
    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Imola/GO 2.0 Q Esport.svm"}
    row = _row_for_track(in_memory_db, TRACK)
    assert row.setup_id == setup_id_before


def test_tracktitan_setup_and_go_archive_for_the_same_track_share_the_lmu_folder(sandbox, in_memory_db):
    # Two different cars' HYMO setups, both installed for the same track
    # (Porsche 963 unrelated to the GO archive below, Oreca 07 the one it
    # attaches to).
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


def test_go_archive_installs_even_without_any_matching_hymo_setup(sandbox, in_memory_db):
    """No gate: a GO archive's <Car>/<Track> share folder is trusted on its
    own - a HYMO setup for that same car+track need never have existed."""
    sandbox.add_go_zip("Ferrari 499P", "Imola", "GO-Ferrari-Mystery.zip", {"go.svm": "x"})

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Imola/go.svm"}
    go_rows = [r for r in in_memory_db.fetch_all_installed_setups() if r.setup_type == "GO"]
    assert len(go_rows) == 1
    assert go_rows[0].car == "Ferrari 499P"


def test_unmapped_go_track_is_ignored_outright_not_installed_under_a_fallback_folder(sandbox, in_memory_db, caplog):
    """An unmatched GO Setups car/track is skipped entirely (never downloaded,
    never installed) rather than landing under a "-GO" placeholder folder -
    see domain.unmatched.UnmatchedTracker, which SlaveManager._process_go
    records it into for the end-of-run correction dialog."""
    car, track = "Ferrari 499P", "Nonexistent Circuit"

    sandbox.add_go_zip(car, track, "GO-Ferrari-Mystery.zip", {"go.svm": "x"})
    with caplog.at_level("WARNING"):
        sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == set()
    assert in_memory_db.fetch_all_installed_setups() == []
    assert "GO Setup not matched" in caplog.text


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
