import hashlib
import json
import threading
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.progress import ProgressKind


def _meta(id="id1", track="Spa", car="Porsche 963", ts=1000):
    return {
        "id": id,
        "title": "T",
        "setupCombos": [{"car": {"name": car}, "track": {"name": track}}],
        "hotlapLink": None,
        "lastUpdatedAt": ts,
        "isBundle": False,
    }


def _remote(name="Spa_Porsche_963_id1_1000.zip", setup_id="id1", ts=1000):
    from clients.dropbox_client import RemoteSetup
    return RemoteSetup(name=name, path_lower="/lmu-setups/" + name.lower(), setup_id=setup_id, ts=ts)


def _go_remote(car="Oreca 07", track="Imola", name="GO-ORECA.zip"):
    from domain.go_setup import RemoteGoSetup
    path_lower = f"/lmu-setups/{car.lower()}/{track.lower()}/{name.lower()}"
    return RemoteGoSetup(name=name, path_lower=path_lower, car=car, track=track)


def _fake_go_download(content=b"go zip content"):
    def _download(path_lower, local_path):
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(content)
        return local
    return _download


def _fake_download(path_lower, local_path):
    """Regular (HYMO) download: a.svm + valid .metadata.json for id1/Spa/Porsche 963/ts=1000."""
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(local, "w") as zf:
        zf.writestr("a.svm", b"svm")
        zf.writestr(".metadata.json", json.dumps(_meta()))
    return local


@pytest.fixture
def sm(mocker, tmp_path):
    mocker.patch("orchestration.slave_manager.DOWNLOAD_PATH", tmp_path)
    from orchestration.slave_manager import SlaveManager
    dbx = MagicMock()
    dbx.list_go_setups.return_value = []
    setup_manager = MagicMock()
    # Matched by default, echoing the raw text straight back as the
    # "official" name - unconfigured, these MagicMock attributes would
    # otherwise auto-vivify as truthy-but-wrong MagicMock instances, and
    # _process/_process_go now skip outright (recording into
    # manager.unmatched) on an unmatched car/track rather than installing
    # under a placeholder name. A test that wants the unmatched path sets
    # one of these to a `lambda _: None` side_effect instead.
    setup_manager.car_manager.get_car_name.side_effect = lambda car: car
    setup_manager.track_manager.get_track_folder_name.side_effect = lambda track: track
    setup_manager.track_manager.get_official_track_name.side_effect = lambda track: track
    database = MagicMock()
    database.fetch_installed_go_setup.return_value = None
    return SlaveManager(dropbox_client=dbx, setup_manager=setup_manager, database=database), dbx, setup_manager, database, tmp_path


def test_skip_when_installed(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = True
    manager._process(_remote())
    dbx.download_to.assert_not_called()
    setup_manager.install_setup.assert_not_called()


def test_download_install_and_metadata(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    dbx.download_to.side_effect = _fake_download

    manager._process(_remote())

    setup_manager.install_setup.assert_called_once()
    from domain.setup import Setup
    (local_arg, setup_arg), kwargs = setup_manager.install_setup.call_args
    assert isinstance(setup_arg, Setup)
    assert setup_arg.id == "id1"
    assert Path(local_arg).name == "Spa_Porsche_963_id1_1000.zip"
    assert kwargs["sha256"] == hashlib.sha256(Path(local_arg).read_bytes()).hexdigest()


def test_missing_metadata_skips_install(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False

    def fake_download(path_lower, local_path):
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(local, "w") as zf:
            zf.writestr("a.svm", b"svm")  # no .metadata.json
        return local

    dbx.download_to.side_effect = fake_download

    manager._process(_remote())

    setup_manager.install_setup.assert_not_called()


def test_process_skips_unmatched_setup_and_records_it(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    dbx.download_to.side_effect = _fake_download
    setup_manager.car_manager.get_car_name.side_effect = lambda car: None

    manager._process(_remote())

    setup_manager.install_setup.assert_not_called()
    assert manager.unmatched.serialize() == [
        {"track": "Spa", "car": "Porsche 963", "source": "dropbox", "trackMatched": True, "carMatched": False},
    ]


def test_process_unmatched_setup_never_emits_start(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    dbx.download_to.side_effect = _fake_download
    setup_manager.track_manager.get_track_folder_name.side_effect = lambda track: None
    events = []
    manager.on_progress = events.append

    manager._process(_remote())

    assert events == []


def test_run_lists_the_dropbox_share(sm):
    manager, dbx, setup_manager, database, tmp = sm
    dbx.list_setups.return_value = []
    manager.run()
    dbx.list_setups.assert_called_once()


# --- on_progress / cancel_event ----------------------------------------------


def test_progress_and_cancel_event_default_to_none(sm):
    manager, dbx, setup_manager, database, tmp = sm
    assert manager.on_progress is None
    assert manager.cancel_event is None


def test_records_progress_event_sequence(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    dbx.list_setups.return_value = [
        _remote(name="a.zip", setup_id="id1"),
        _remote(name="b.zip", setup_id="id2"),
    ]
    dbx.download_to.side_effect = _fake_download

    events = []
    manager.on_progress = events.append

    manager.run()

    assert [e.kind for e in events] == [
        ProgressKind.START, ProgressKind.INSTALL,
        ProgressKind.START, ProgressKind.INSTALL,
        ProgressKind.FINISH,
    ]


def test_cancel_event_truncates_remaining_work(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    dbx.list_setups.return_value = [
        _remote(name="a.zip", setup_id="id1"),
        _remote(name="b.zip", setup_id="id2"),
    ]
    dbx.download_to.side_effect = _fake_download

    cancel_event = threading.Event()
    manager.cancel_event = cancel_event
    # Cancel as soon as the first setup finishes installing, before the loop
    # moves on to the second.
    setup_manager.install_setup.side_effect = lambda *a, **k: cancel_event.set()

    events = []
    manager.on_progress = events.append

    manager.run()

    assert setup_manager.install_setup.call_count == 1
    assert events[-1].kind == ProgressKind.STOPPED


def test_cancel_event_set_before_run_processes_nothing(sm):
    manager, dbx, setup_manager, database, tmp = sm
    dbx.list_setups.return_value = [_remote(name="a.zip", setup_id="id1")]

    manager.cancel_event = threading.Event()
    manager.cancel_event.set()

    events = []
    manager.on_progress = events.append

    manager.run()

    setup_manager.install_setup.assert_not_called()
    assert [e.kind for e in events] == [ProgressKind.STOPPED]


def test_omitting_on_progress_and_cancel_event_runs_normally(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    dbx.list_setups.return_value = [_remote(name="a.zip", setup_id="id1")]
    dbx.download_to.side_effect = _fake_download

    manager.run()  # on_progress/cancel_event both left at their None defaults

    setup_manager.install_setup.assert_called_once()


# --- GO Setups (_process_go) --------------------------------------------------


def test_process_go_first_time_mints_uuid_and_installs(sm):
    import uuid as uuid_module
    from core.config import GO_SETUP_FILE_EXTENSIONS
    manager, dbx, setup_manager, database, tmp = sm
    content = b"go zip v1"
    dbx.download_to.side_effect = _fake_go_download(content)
    events = []
    manager.on_progress = events.append

    manager._process_go(_go_remote())

    database.fetch_installed_go_setup.assert_called_once_with("Oreca 07", "Imola")
    setup_manager.install_setup.assert_called_once()
    (local_arg, setup_arg), kwargs = setup_manager.install_setup.call_args
    assert kwargs["extensions"] == GO_SETUP_FILE_EXTENSIONS
    assert kwargs["setup_type"] == "GO"
    assert kwargs["sha256"] == hashlib.sha256(content).hexdigest()
    assert uuid_module.UUID(setup_arg.id)  # plain UUID, no prefix
    assert setup_arg.car == "Oreca 07"
    assert setup_arg.track == "Imola"
    assert [e.kind for e in events] == [ProgressKind.START, ProgressKind.INSTALL]


def test_process_go_unchanged_skips_install_even_with_different_filename(sm):
    manager, dbx, setup_manager, database, tmp = sm
    content = b"go zip v1"
    digest = hashlib.sha256(content).hexdigest()
    existing = MagicMock(setup_id="go-existing-id", sha256=digest)
    database.fetch_installed_go_setup.return_value = existing
    dbx.download_to.side_effect = _fake_go_download(content)
    events = []
    manager.on_progress = events.append

    manager._process_go(_go_remote(name="GO-Renamed.zip"))

    setup_manager.install_setup.assert_not_called()
    assert [e.kind for e in events] == [ProgressKind.START]


def test_process_go_skips_unmatched_and_records_it_without_downloading(sm):
    manager, dbx, setup_manager, database, tmp = sm
    setup_manager.track_manager.get_official_track_name.side_effect = lambda track: None

    manager._process_go(_go_remote())

    dbx.download_to.assert_not_called()
    setup_manager.install_setup.assert_not_called()
    assert manager.unmatched.serialize() == [
        {"track": "Imola", "car": "Oreca 07", "source": "dropbox", "trackMatched": False, "carMatched": True},
    ]


def test_process_go_changed_content_reuses_the_existing_setup_id(sm):
    manager, dbx, setup_manager, database, tmp = sm
    old_digest = hashlib.sha256(b"go zip v1").hexdigest()
    existing = MagicMock(setup_id="go-existing-id", sha256=old_digest)
    database.fetch_installed_go_setup.return_value = existing
    new_content = b"go zip v2, totally different internal files"
    dbx.download_to.side_effect = _fake_go_download(new_content)

    manager._process_go(_go_remote())

    (local_arg, setup_arg), kwargs = setup_manager.install_setup.call_args
    assert setup_arg.id == "go-existing-id"
    assert kwargs["sha256"] == hashlib.sha256(new_content).hexdigest()


# --- run(): regular + GO in one pass ------------------------------------------


def test_run_processes_regular_then_go_remote_ending_in_one_finish(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    hymo_remote = _remote(name="a.zip", setup_id="id1")
    go_remote = _go_remote()
    dbx.list_setups.return_value = [hymo_remote]
    dbx.list_go_setups.return_value = [go_remote]

    def fake_download(path_lower, local_path):
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        if path_lower == hymo_remote.path_lower:
            with zipfile.ZipFile(local, "w") as zf:
                zf.writestr("a.svm", b"svm")
                zf.writestr(".metadata.json", json.dumps(_meta(id="id1", ts=1000)))
        else:
            local.write_bytes(b"go content")
        return local

    dbx.download_to.side_effect = fake_download

    events = []
    manager.on_progress = events.append

    manager.run()

    assert setup_manager.install_setup.call_count == 2
    assert events[-1].kind == ProgressKind.FINISH


def test_cancel_after_regular_loop_stops_before_go_loop_starts(sm):
    manager, dbx, setup_manager, database, tmp = sm
    database.is_installed_last_version.return_value = False
    dbx.list_setups.return_value = [_remote(name="a.zip", setup_id="id1")]
    dbx.list_go_setups.return_value = [_go_remote()]
    dbx.download_to.side_effect = _fake_download

    cancel_event = threading.Event()
    manager.cancel_event = cancel_event
    setup_manager.install_setup.side_effect = lambda *a, **k: cancel_event.set()

    events = []
    manager.on_progress = events.append

    manager.run()

    setup_manager.install_setup.assert_called_once()
    assert events[-1].kind == ProgressKind.STOPPED


# --- unmatched car/track surfaced on the run()-level FINISH/STOPPED events ----


def test_finish_event_carries_the_unmatched_list(sm):
    manager, dbx, setup_manager, database, tmp = sm
    dbx.list_setups.return_value = []
    dbx.list_go_setups.return_value = [_go_remote()]
    setup_manager.track_manager.get_official_track_name.side_effect = lambda track: None
    events = []
    manager.on_progress = events.append

    manager.run()

    finish = next(e for e in events if e.kind == ProgressKind.FINISH)
    assert finish.unmatched == [
        {"track": "Imola", "car": "Oreca 07", "source": "dropbox", "trackMatched": False, "carMatched": True},
    ]


def test_finish_event_unmatched_is_none_when_everything_matched(sm):
    manager, dbx, setup_manager, database, tmp = sm
    dbx.list_setups.return_value = []
    events = []
    manager.on_progress = events.append

    manager.run()

    finish = next(e for e in events if e.kind == ProgressKind.FINISH)
    assert finish.unmatched is None


def test_a_shared_unmatched_tracker_can_be_injected(mocker, tmp_path):
    from orchestration.slave_manager import SlaveManager
    from domain.unmatched import UnmatchedTracker

    mocker.patch("orchestration.slave_manager.DOWNLOAD_PATH", tmp_path)
    dbx = MagicMock()
    dbx.list_setups.return_value = []
    dbx.list_go_setups.return_value = [_go_remote()]
    setup_manager = MagicMock()
    setup_manager.track_manager.get_official_track_name.side_effect = lambda track: None
    database = MagicMock()
    tracker = UnmatchedTracker()

    manager = SlaveManager(dropbox_client=dbx, setup_manager=setup_manager, database=database, unmatched=tracker)
    manager.run()

    assert manager.unmatched is tracker
    assert tracker.serialize() == [
        {"track": "Imola", "car": "Oreca 07", "source": "dropbox", "trackMatched": False, "carMatched": True},
    ]
