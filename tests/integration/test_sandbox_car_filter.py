"""Car filter (settings.db config "cars"): filtered-out setups are neither
downloaded nor recorded as unmatched, selected ones still flow, manual uploads
are never filtered. Drives the real managers through the sandbox; only the
external systems are mocked."""
import logging

import pytest

from sandbox_harness import make_setup

ID_963 = "aaaaaaaa-bbbb-4ccc-8ddd-000000000963"
ID_ORECA = "aaaaaaaa-bbbb-4ccc-8ddd-000000000007"
CARS = [("963", "Porsche 963"), ("oreca", "Oreca 07")]


def _set_filter(all_cars: bool, selected: list[str]) -> None:
    from core import settings_db
    settings_db.save_config({"cars": {"all": all_cars, "selected": selected}})


@pytest.fixture(autouse=True)
def _world(sandbox):
    sandbox.set_tracks([("spa", "Spa")])
    sandbox.set_cars(CARS)
    sandbox.write_catalog([
        make_setup(ID_963, "Spa", car="Porsche 963"),
        make_setup(ID_ORECA, "Spa", car="Oreca 07"),
    ])
    sandbox.add_archive(ID_963, {"p.svm": "p"})
    sandbox.add_archive(ID_ORECA, {"o.svm": "o"})
    return sandbox


@pytest.fixture
def tt_downloads(mocker):
    from clients.mocks.mock_track_titan_client import MockTrackTitanClient
    return mocker.spy(MockTrackTitanClient, "download_link")


def _downloaded_ids(spy) -> set[str]:
    return {c.args[1] for c in spy.call_args_list}


# ----- MASTER ----------------------------------------------------------------


def test_master_all_true_publishes_everything(sandbox):
    sandbox.run_master()
    assert len(sandbox.share_names()) == 2


def test_master_publishes_only_selected_and_never_downloads_the_rest(sandbox, tt_downloads):
    _set_filter(False, ["Porsche 963"])

    sandbox.run_master()

    assert {n.split("_")[-2] for n in sandbox.share_names()} == {ID_963}
    assert _downloaded_ids(tt_downloads) == {ID_963}


def test_master_filtered_car_is_not_recorded_unmatched(sandbox):
    from domain.unmatched import UnmatchedTracker
    from orchestration.download_manager import DownloadManager
    from orchestration.master_manager import MasterManager
    from processing.car_manager import CarManager
    from processing.track_manager import TrackManager

    _set_filter(False, ["Porsche 963"])
    unmatched = UnmatchedTracker()
    MasterManager(
        download_manager=DownloadManager(database=None, client=sandbox.tracktitan()),
        dropbox_client=sandbox.dropbox(), car_manager=CarManager(),
        track_manager=TrackManager(), unmatched=unmatched,
    ).run()

    assert unmatched.serialize() is None


def test_master_empty_selection_publishes_nothing(sandbox, tt_downloads):
    _set_filter(False, [])
    sandbox.run_master()
    assert sandbox.share_names() == set()
    tt_downloads.assert_not_called()


def test_master_manual_upload_is_not_filtered(sandbox):
    _set_filter(False, [])  # nothing selected at all
    setup = sandbox.add_manual_hymo_zip("Oreca 07", "Spa", {"m.svm": "m"})
    assert any(setup.id in n for n in sandbox.share_names())


# ----- SLAVE (HYMO packages) -------------------------------------------------


def _publish_both(sandbox) -> None:
    sandbox.run_master()
    assert len(sandbox.share_names()) == 2


def test_slave_installs_only_selected_cars_and_skips_download(sandbox, in_memory_db, mocker):
    _publish_both(sandbox)
    _set_filter(False, ["Porsche 963"])
    from clients.mocks.mock_dropbox_client import MockDropboxClient
    dl = mocker.spy(MockDropboxClient, "download_to")

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Spa/p.svm"}
    assert len(dl.call_args_list) == 1
    assert in_memory_db.fetch_installed_setup(ID_ORECA) is None


def test_slave_all_true_installs_everything(sandbox, in_memory_db):
    _publish_both(sandbox)
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/p.svm", "Spa/o.svm"}


def test_slave_filtered_car_not_recorded_unmatched(sandbox, in_memory_db):
    from domain.unmatched import UnmatchedTracker
    from orchestration.slave_manager import SlaveManager

    _publish_both(sandbox)
    _set_filter(False, ["Porsche 963"])
    unmatched = UnmatchedTracker()
    SlaveManager(
        dropbox_client=sandbox.dropbox(), setup_manager=sandbox.setup_manager(in_memory_db),
        database=in_memory_db, unmatched=unmatched,
    ).run()
    assert unmatched.serialize() is None


def test_slave_picks_up_a_car_once_the_filter_is_widened(sandbox, in_memory_db):
    _publish_both(sandbox)
    _set_filter(False, ["Porsche 963"])
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/p.svm"}

    _set_filter(False, ["Porsche 963", "Oreca 07"])
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/p.svm", "Spa/o.svm"}


def test_slave_manual_hymo_upload_with_unselected_car_is_still_installed_when_filter_off(sandbox, in_memory_db):
    sandbox.add_manual_hymo_zip("Oreca 07", "Spa", {"m.svm": "m"})
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/m.svm"}


# ----- SLAVE (GO setups) -----------------------------------------------------


def test_slave_go_setup_for_unselected_car_is_not_downloaded_or_unmatched(sandbox, in_memory_db, mocker):
    from clients.mocks.mock_dropbox_client import MockDropboxClient
    from domain.unmatched import UnmatchedTracker
    from orchestration.slave_manager import SlaveManager

    sandbox.add_go_zip("Oreca 07", "Spa", "GO-1.zip", {"GO q.svm": "x"})
    sandbox.add_go_zip("Porsche 963", "Spa", "GO-2.zip", {"GO r.svm": "y"})
    _set_filter(False, ["Porsche 963"])
    dl = mocker.spy(MockDropboxClient, "download_to")
    unmatched = UnmatchedTracker()

    SlaveManager(
        dropbox_client=sandbox.dropbox(), setup_manager=sandbox.setup_manager(in_memory_db),
        database=in_memory_db, unmatched=unmatched,
    ).run()

    assert sandbox.installed_files() == {"Spa/GO r.svm"}
    assert len(dl.call_args_list) == 1
    assert unmatched.serialize() is None


# ----- FULL (main.run_full) --------------------------------------------------


@pytest.fixture
def wired(sandbox, tmp_path, mocker):
    mocker.patch("clients.protocols.MOCK_TRACKTITAN", True)
    mocker.patch("clients.mocks.mock_track_titan_client.SANDBOX_TRACKTITAN_PATH", sandbox.catalog_dir)
    mocker.patch("core.config.LMU_SETUPS_BASE_PATH", sandbox.lmu)
    mocker.patch("processing.setup_manager.LMU_SETUPS_BASE_PATH", sandbox.lmu)
    mocker.patch("domain.setup_db.DB_PATH", tmp_path / "sandbox.db")
    return sandbox


def test_run_full_skips_unselected_car_without_downloading(wired, tt_downloads):
    import main
    _set_filter(False, ["Oreca 07"])

    main.run_full(logging.getLogger("TrackTitanDownloader"))

    assert wired.installed_files() == {"Spa/o.svm"}
    assert _downloaded_ids(tt_downloads) == {ID_ORECA}


def test_run_full_filtered_car_is_not_reported_unmatched(wired):
    import main
    from core.progress import ProgressKind
    _set_filter(False, ["Oreca 07"])
    events = []

    main.run_full(logging.getLogger("TrackTitanDownloader"), on_progress=events.append)

    assert events[-1].kind == ProgressKind.FINISH
    assert events[-1].unmatched is None


def test_run_full_all_true_installs_everything(wired):
    import main
    main.run_full(logging.getLogger("TrackTitanDownloader"))
    assert wired.installed_files() == {"Spa/p.svm", "Spa/o.svm"}
