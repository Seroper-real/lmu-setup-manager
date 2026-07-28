"""Manually-uploaded HYMO-type archives (the "Carica Setup" tab, master mode)
must be indistinguishable from a TrackTitan-published one once they hit the
share: same HYMO- branded filename scheme, same embedded .metadata.json, so
SlaveManager's install-phase code path (SlaveManager._process) never needs to
know or care which one produced a given zip.
"""
import pytest

from sandbox_harness import make_setup

CAR = "Porsche 963"
TRACK = "Spa"


@pytest.fixture(autouse=True)
def _tracks(sandbox):
    sandbox.set_tracks([("spa", "Spa")])


def test_manually_uploaded_hymo_setup_installs_like_a_tracktitan_one(sandbox, in_memory_db):
    setup = sandbox.add_manual_hymo_zip(CAR, TRACK, {"quali.svm": "manual-v1"})

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Spa/quali.svm"}
    row = in_memory_db.fetch_installed_setup(setup.id)
    assert row is not None
    assert row.setup_type == "HYMO"
    assert row.car == CAR
    assert row.track == TRACK
    assert row.track_found is True
    assert row.sha256 is not None


def test_manually_uploaded_hymo_setup_is_not_reinstalled_on_a_second_slave_run(sandbox, in_memory_db, mocker):
    sandbox.add_manual_hymo_zip(CAR, TRACK, {"quali.svm": "manual-v1"})
    sandbox.run_slave(in_memory_db)

    from processing.setup_manager import SetupManager
    install_spy = mocker.spy(SetupManager, "install_setup")

    sandbox.run_slave(in_memory_db)

    install_spy.assert_not_called()
    assert sandbox.installed_files() == {"Spa/quali.svm"}


def test_manually_uploaded_hymo_zip_is_never_picked_up_by_list_go_setups(sandbox):
    sandbox.add_manual_hymo_zip(CAR, TRACK, {"quali.svm": "manual-v1"})

    dbx = sandbox.dropbox()

    assert len(dbx.list_setups()) == 1
    assert dbx.list_go_setups() == []


def test_manually_uploaded_and_tracktitan_hymo_setups_coexist_in_one_slave_run(
    sandbox, in_memory_db,
):
    """A manual upload for one car/track and an automated TrackTitan publish
    for another must both install cleanly in the same run, proving the manual
    one rides the exact same list_setups()/_process() path rather than a
    parallel one that could silently diverge."""
    tt_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    # set_cars() replaces (not merges with) the harness's default "963" ->
    # "Porsche 963" seed, so it must be re-included alongside "Cadillac Race".
    sandbox.set_cars([("963", "Porsche 963"), ("cadillac race", "Cadillac Race")])
    sandbox.write_catalog([make_setup(tt_id, "Spa", car="Cadillac Race")])
    sandbox.add_archive(tt_id, {"tt_quali.svm": "tt"})
    sandbox.run_master()

    manual = sandbox.add_manual_hymo_zip(CAR, TRACK, {"manual_quali.svm": "manual"})

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Spa/tt_quali.svm", "Spa/manual_quali.svm"}
    assert in_memory_db.fetch_installed_setup(tt_id).setup_type == "HYMO"
    assert in_memory_db.fetch_installed_setup(manual.id).setup_type == "HYMO"


# ----- full master-upload / slave-install update sequence --------------------


def test_manual_upload_update_sequence_across_master_and_slave_runs(sandbox, in_memory_db, mocker):
    """The full lifecycle a manual re-upload must go through:

    1) master: manual upload of a setup
    2) slave: download and install it
    3) slave: download again - must be skipped, already latest
    4) master: manual re-upload of the same car/track - must be an update
       (same id, previous share zip deleted)
    5) slave: download again - must be reinstalled/updated
    """
    from processing.setup_manager import SetupManager

    mock_time = mocker.patch("processing.manual_upload.time")
    mock_time.time.return_value = 1700000000.0

    # 1) master: manual upload
    first = sandbox.add_manual_hymo_zip(CAR, TRACK, {"quali_v1.svm": "v1"})
    assert sandbox.share_names() == {first.remote_filename}

    # 2) slave: download and install
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/quali_v1.svm"}
    row = in_memory_db.fetch_installed_setup(first.id)
    assert row is not None
    assert row.setup_type == "HYMO"

    # 3) slave: re-run, must be skipped (already the latest version)
    install_spy = mocker.spy(SetupManager, "install_setup")
    sandbox.run_slave(in_memory_db)
    install_spy.assert_not_called()
    assert sandbox.installed_files() == {"Spa/quali_v1.svm"}

    # 4) master: manual re-upload of the same car/track - must be an update
    mock_time.time.return_value = 1700009999.0
    second = sandbox.add_manual_hymo_zip(CAR, TRACK, {"quali_v2.svm": "v2"})
    assert second.id == first.id, "a re-upload for the same car/track/type must reuse the previous id"
    assert sandbox.share_names() == {second.remote_filename}, \
        "the previous share version must be deleted after the new upload succeeds"

    # 5) slave: re-run, must reinstall/update
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/quali_v2.svm"}, \
        "the superseded .svm must be replaced, not left alongside the new one"
    assert in_memory_db.is_installed_last_version(first.id, second.last_updated) is True
