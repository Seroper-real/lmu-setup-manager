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


@pytest.fixture
def sm(mocker, tmp_path):
    mocker.patch("orchestration.slave_manager.DOWNLOAD_PATH", tmp_path)
    from orchestration.slave_manager import SlaveManager
    dbx = MagicMock()
    setup_manager = MagicMock()
    database = MagicMock()
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

    def fake_download(path_lower, local_path):
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(local, "w") as zf:
            zf.writestr("a.svm", b"svm")
            zf.writestr(".metadata.json", json.dumps(_meta(id="id1", ts=1000)))
        return local

    dbx.download_to.side_effect = fake_download

    manager._process(_remote())

    setup_manager.install_setup.assert_called_once()
    from domain.setup import Setup
    local_arg, setup_arg = setup_manager.install_setup.call_args[0]
    assert isinstance(setup_arg, Setup)
    assert setup_arg.id == "id1"
    assert Path(local_arg).name == "Spa_Porsche_963_id1_1000.zip"


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


def test_run_housekeeps_and_lists(sm):
    manager, dbx, setup_manager, database, tmp = sm
    dbx.list_setups.return_value = []
    manager.run()
    setup_manager.update_tracks_not_found.assert_called_once()
    dbx.list_setups.assert_called_once()


# --- on_progress / cancel_event ----------------------------------------------


def _fake_download(path_lower, local_path):
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(local, "w") as zf:
        zf.writestr("a.svm", b"svm")
        zf.writestr(".metadata.json", json.dumps(_meta()))
    return local


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
