import json
import threading
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.progress import ProgressKind


def _setup(id="id1", ts=2000, bundle=False, track="Spa", car="Porsche 963"):
    from domain.setup import Setup
    return Setup({
        "id": id,
        "title": "T",
        "setupCombos": [{"car": {"name": car}, "track": {"name": track}}],
        "hotlapLink": None,
        "lastUpdatedAt": ts,
        "isBundle": bundle,
    })


def _remote(name, setup_id, ts):
    from clients.dropbox_client import RemoteSetup
    return RemoteSetup(name=name, path_lower="/lmu-setups/" + name.lower(), setup_id=setup_id, ts=ts)


@pytest.fixture
def mm(mocker, tmp_path):
    """A MasterManager wired to mocks. workers=1 keeps the assertions deterministic;
    the pool itself is exercised by the workers>1 tests below."""
    mocker.patch("orchestration.master_manager.DOWNLOAD_PATH", tmp_path)
    mocker.patch("orchestration.master_manager.CLEAN_DOWNLOAD", False)  # keep files for inspection
    mocker.patch("orchestration.master_manager.SETUP_FILE_EXTENSIONS", {".svm"})
    from orchestration.master_manager import MasterManager
    dm = MagicMock()
    dbx = MagicMock()
    dbx.list_setups.return_value = []
    manager = MasterManager(download_manager=dm, dropbox_client=dbx, workers=1)
    return manager, dm, dbx, tmp_path


def _pages(dm, *pages):
    """Feed the producer loop: each page, then the empty page that ends it."""
    dm.get_setups_list.side_effect = [*pages, []]


def _downloadable(dm, tmp, name="orig.zip"):
    orig = tmp / name
    orig.write_bytes(b"zip")
    dm.download.return_value = orig
    return orig


def _fake_extraction(mocker, svm_files):
    mocker.patch("orchestration.master_manager.unzip_recursive", side_effect=lambda z, d: Path(d).mkdir(parents=True, exist_ok=True))
    mocker.patch("orchestration.master_manager.find_files_recursive", return_value=svm_files)


def _svm(tmp, name="a.svm"):
    svm = tmp / "src" / name
    svm.parent.mkdir(parents=True, exist_ok=True)
    svm.write_bytes(b"svm")
    return svm


def test_skip_when_up_to_date(mm):
    manager, dm, dbx, tmp = mm
    dbx.list_setups.return_value = [_remote("HYMO-Spa_Porsche_963_id1_1000.zip", "id1", 1000)]
    _pages(dm, [_setup(id="id1", ts=1000)])

    manager.run()

    dm.download.assert_not_called()
    dbx.upload.assert_not_called()


def test_skip_bundle(mm):
    manager, dm, dbx, tmp = mm
    _pages(dm, [_setup(id="b1", bundle=True)])

    manager.run()

    dm.download.assert_not_called()


def test_upload_when_new(mm, mocker):
    manager, dm, dbx, tmp = mm
    setup = _setup(id="id1", ts=2000)
    _pages(dm, [setup])
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()

    dbx.upload.assert_called_once()
    pkg_arg, name_arg = dbx.upload.call_args[0]
    assert name_arg == setup.remote_relative_path
    with zipfile.ZipFile(pkg_arg) as zf:
        names = zf.namelist()
        assert "a.svm" in names
        assert ".metadata.json" in names
        assert json.loads(zf.read(".metadata.json"))["id"] == "id1"
    dbx.delete.assert_not_called()


def test_upload_and_delete_when_outdated(mm, mocker):
    manager, dm, dbx, tmp = mm
    dbx.list_setups.return_value = [_remote("HYMO-Spa_Porsche_963_id1_1000.zip", "id1", 1000)]
    _pages(dm, [_setup(id="id1", ts=2000)])
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()

    dbx.upload.assert_called_once()
    dbx.delete.assert_called_once_with("/lmu-setups/hymo-spa_porsche_963_id1_1000.zip")


def test_skip_when_no_svm(mm, mocker):
    manager, dm, dbx, tmp = mm
    _pages(dm, [_setup(id="id1", ts=2000)])
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [])

    manager.run()

    dbx.upload.assert_not_called()
    dbx.delete.assert_not_called()


def test_cleanup_removes_files_when_enabled(mm, mocker):
    manager, dm, dbx, tmp = mm
    mocker.patch("orchestration.master_manager.CLEAN_DOWNLOAD", True)
    setup = _setup(id="id1", ts=2000)
    _pages(dm, [setup])
    orig = _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()

    # original + repackaged zip cleaned, extraction dir removed
    assert not orig.exists()
    assert not (tmp / setup.remote_filename).exists()
    assert not (tmp / setup.id).exists()


# --- the upload pipeline ---


def test_every_setup_is_uploaded_exactly_once_with_a_worker_pool(mm, mocker):
    manager, dm, dbx, tmp = mm
    manager.workers = 4
    setups = [_setup(id=f"id{i}", ts=2000, car=f"Car {i}") for i in range(12)]
    _pages(dm, setups[:8], setups[8:])
    # Each setup gets its own source zip, as it would in a real run.
    dm.download.side_effect = lambda s: _downloadable(dm, tmp, f"{s.id}.zip")
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()

    uploaded = [call[0][1] for call in dbx.upload.call_args_list]
    assert sorted(uploaded) == sorted(s.remote_relative_path for s in setups)


def test_a_failing_worker_does_not_abort_the_run(mm, mocker):
    manager, dm, dbx, tmp = mm
    manager.workers = 4
    setups = [_setup(id=f"id{i}", ts=2000, car=f"Car {i}") for i in range(4)]
    _pages(dm, setups)
    dm.download.side_effect = lambda s: _downloadable(dm, tmp, f"{s.id}.zip")
    _fake_extraction(mocker, [_svm(tmp)])

    def explode(package_path, remote_name):
        if remote_name == setups[1].remote_relative_path:
            raise RuntimeError("dropbox is down")

    dbx.upload.side_effect = explode

    manager.run()  # must not raise

    # The other three still went up.
    assert dbx.upload.call_count == 4


def test_same_id_on_two_pages_is_published_once(mm, mocker):
    manager, dm, dbx, tmp = mm
    setup = _setup(id="id1", ts=2000)
    _pages(dm, [setup], [setup])  # the API handed the same id back twice
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()

    dbx.upload.assert_called_once()


def test_each_worker_builds_its_own_dropbox_client(mm, mocker):
    """The Dropbox SDK wraps a requests.Session, which is not thread-safe: workers
    must never share one."""
    manager, dm, dbx, tmp = mm
    manager.workers = 4
    built = []

    def factory():
        client = MagicMock()
        built.append(client)
        return client

    manager.client_factory = factory
    setups = [_setup(id=f"id{i}", ts=2000, car=f"Car {i}") for i in range(8)]
    _pages(dm, setups)
    dm.download.side_effect = lambda s: _downloadable(dm, tmp, f"{s.id}.zip")
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()

    # The shared client is only used to list the share, never to upload.
    dbx.upload.assert_not_called()
    assert 1 <= len(built) <= manager.workers
    assert sum(c.upload.call_count for c in built) == len(setups)


# --- on_progress / cancel_event ----------------------------------------------


def test_progress_and_cancel_event_default_to_none(mm):
    manager, dm, dbx, tmp = mm
    assert manager.on_progress is None
    assert manager.cancel_event is None


def test_records_progress_event_sequence(mm, mocker):
    manager, dm, dbx, tmp = mm
    setup = _setup(id="id1", ts=2000)
    _pages(dm, [setup])
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])
    events = []
    manager.on_progress = events.append

    manager.run()

    assert [e.kind for e in events] == [ProgressKind.START, ProgressKind.INSTALL, ProgressKind.FINISH]


def test_omitting_on_progress_and_cancel_event_runs_to_completion(mm, mocker):
    manager, dm, dbx, tmp = mm
    setup = _setup(id="id1", ts=2000)
    _pages(dm, [setup])
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()  # on_progress/cancel_event both left at their None defaults

    dbx.upload.assert_called_once()


def test_cancel_event_stops_dispatching_further_work(mm, mocker):
    manager, dm, dbx, tmp = mm
    setups = [_setup(id=f"id{i}", ts=2000, car=f"Car {i}") for i in range(4)]
    _pages(dm, setups)
    dm.download.side_effect = lambda s: _downloadable(dm, tmp, f"{s.id}.zip")
    _fake_extraction(mocker, [_svm(tmp)])

    cancel_event = threading.Event()
    manager.cancel_event = cancel_event

    # Cancel as soon as the first setup is dispatched, so later setups on the
    # same page are never handed to the pool - in-flight work is unaffected.
    original_dispatch = manager._dispatch

    def dispatch_then_cancel(setup, *args, **kwargs):
        original_dispatch(setup, *args, **kwargs)
        cancel_event.set()

    mocker.patch.object(manager, "_dispatch", side_effect=dispatch_then_cancel)

    events = []
    manager.on_progress = events.append

    manager.run()

    assert dbx.upload.call_count < len(setups)
    assert events[-1].kind == ProgressKind.STOPPED


def test_cancel_event_set_before_run_dispatches_nothing(mm, mocker):
    manager, dm, dbx, tmp = mm
    setup = _setup(id="id1", ts=2000)
    _pages(dm, [setup])

    manager.cancel_event = threading.Event()
    manager.cancel_event.set()

    manager.run()

    dm.download.assert_not_called()
    dbx.upload.assert_not_called()
