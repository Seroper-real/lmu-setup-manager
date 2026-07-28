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


def _remote(path, setup_id, ts):
    """`path` is the share-relative path (folder(s) + filename); RemoteSetup.name
    (like the real Dropbox SDK's entry.name) is always the bare filename."""
    from clients.dropbox_client import RemoteSetup
    bare_name = path.rsplit("/", 1)[-1]
    return RemoteSetup(name=bare_name, path_lower="/lmu-setups/" + path.lower(), setup_id=setup_id, ts=ts)


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
    dbx.remote_path.side_effect = lambda rel: f"/lmu-setups/{rel}"
    # Matched by default, echoing the raw text straight back as the
    # "official" name - equivalent to every setup in this module's
    # pre-mapping test data (Porsche 963, BMW M4, Spa, Imola...) resolving to
    # itself, byte for byte, same as the old None-means-unofficialized
    # fallback used to produce for text with nothing sanitize_identity would
    # touch. A test that needs a genuinely different officialized name (or an
    # unmatched one) overrides .side_effect (not .return_value - side_effect
    # takes priority over it once set) below.
    car_manager = MagicMock()
    car_manager.get_car_name.side_effect = lambda car: car
    track_manager = MagicMock()
    track_manager.get_official_track_name.side_effect = lambda track: track
    manager = MasterManager(
        download_manager=dm, dropbox_client=dbx, workers=1,
        car_manager=car_manager, track_manager=track_manager,
    )
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
    # Already-nested path, matching remote_relative_path exactly (car/track
    # unchanged from _setup()'s defaults): a true no-op, not a relocation.
    dbx.list_setups.return_value = [_remote("Porsche 963/Spa/HYMO-Spa_Porsche_963_id1_1000.zip", "id1", 1000)]
    _pages(dm, [_setup(id="id1", ts=1000)])

    manager.run()

    dm.download.assert_not_called()
    dbx.upload.assert_not_called()
    dbx.move.assert_not_called()


def test_relocates_legacy_flat_layout_without_republishing(mm):
    manager, dm, dbx, tmp = mm
    # Old layout: flat <car>/<file>.zip, no track segment.
    dbx.list_setups.return_value = [_remote("Porsche_963/HYMO-Spa_Porsche_963_id1_1000.zip", "id1", 1000)]
    _pages(dm, [_setup(id="id1", ts=1000)])

    manager.run()

    dm.download.assert_not_called()
    dbx.upload.assert_not_called()
    dbx.delete.assert_not_called()
    dbx.move.assert_called_once_with(
        "/lmu-setups/porsche_963/hymo-spa_porsche_963_id1_1000.zip",
        "/lmu-setups/Porsche 963/Spa/HYMO-Spa_Porsche_963_id1_1000.zip",
    )


def test_relocate_failure_does_not_abort_the_run(mm):
    manager, dm, dbx, tmp = mm
    dbx.list_setups.return_value = [
        _remote("Porsche_963/HYMO-Spa_Porsche_963_id1_1000.zip", "id1", 1000),
        _remote("BMW_M4/HYMO-Imola_BMW_M4_id2_1000.zip", "id2", 1000),
    ]
    dbx.move.side_effect = RuntimeError("dropbox is down")
    _pages(dm, [_setup(id="id1", ts=1000), _setup(id="id2", ts=1000, track="Imola", car="BMW M4")])

    manager.run()  # must not raise

    assert dbx.move.call_count == 2
    dm.download.assert_not_called()


def test_relocate_auth_error_propagates_and_stops_the_run(mm):
    """Unlike a generic failure (see the test above), an AuthError must not be
    swallowed - it needs to reach gui/api.py's re-authentication dialog - so
    the run aborts at the first one instead of trying the rest."""
    from core.errors import AuthError
    manager, dm, dbx, tmp = mm
    dbx.list_setups.return_value = [
        _remote("Porsche_963/HYMO-Spa_Porsche_963_id1_1000.zip", "id1", 1000),
        _remote("BMW_M4/HYMO-Imola_BMW_M4_id2_1000.zip", "id2", 1000),
    ]
    dbx.move.side_effect = AuthError("token missing scope", code="dropbox_scope")
    _pages(dm, [_setup(id="id1", ts=1000), _setup(id="id2", ts=1000, track="Imola", car="BMW M4")])

    with pytest.raises(AuthError):
        manager.run()

    assert dbx.move.call_count == 1
    dm.download.assert_not_called()


def test_skip_bundle(mm):
    manager, dm, dbx, tmp = mm
    _pages(dm, [_setup(id="b1", bundle=True)])

    manager.run()

    dm.download.assert_not_called()


# --- unmatched car/track: ignored outright, recorded for the correction dialog -


@pytest.mark.parametrize("break_track, break_car", [
    pytest.param(True, False, id="track_unmatched"),
    pytest.param(False, True, id="car_unmatched"),
    pytest.param(True, True, id="both_unmatched"),
])
def test_unmatched_setup_is_never_downloaded_or_published(mm, break_track, break_car):
    manager, dm, dbx, tmp = mm
    if break_track:
        manager.track_manager.get_official_track_name.side_effect = lambda track: None
    if break_car:
        manager.car_manager.get_car_name.side_effect = lambda car: None
    _pages(dm, [_setup(id="id1", ts=2000)])

    manager.run()

    dm.download.assert_not_called()
    dbx.upload.assert_not_called()


def test_unmatched_setup_is_recorded_with_raw_track_and_car(mm):
    manager, dm, dbx, tmp = mm
    manager.car_manager.get_car_name.side_effect = lambda car: None
    _pages(dm, [_setup(id="id1", ts=2000, track="Mystery Circuit", car="Mystery Car")])

    manager.run()

    assert manager.unmatched.serialize() == [
        {"track": "Mystery Circuit", "car": "Mystery Car", "source": "tracktitan", "trackMatched": True, "carMatched": False},
    ]


def test_unmatched_setups_are_deduped_across_the_run(mm):
    manager, dm, dbx, tmp = mm
    manager.car_manager.get_car_name.side_effect = lambda car: None
    _pages(dm, [
        _setup(id="id1", ts=2000, track="Mystery Circuit", car="Mystery Car"),
        _setup(id="id2", ts=2000, track="Mystery Circuit", car="Mystery Car"),
    ])

    manager.run()

    assert manager.unmatched.serialize() == [
        {"track": "Mystery Circuit", "car": "Mystery Car", "source": "tracktitan", "trackMatched": True, "carMatched": False},
    ]


def test_finish_event_carries_the_unmatched_list(mm):
    manager, dm, dbx, tmp = mm
    manager.car_manager.get_car_name.side_effect = lambda car: None
    _pages(dm, [_setup(id="id1", ts=2000, track="Mystery Circuit", car="Mystery Car")])
    events = []
    manager.on_progress = events.append

    manager.run()

    finish = next(e for e in events if e.kind == ProgressKind.FINISH)
    assert finish.unmatched == [
        {"track": "Mystery Circuit", "car": "Mystery Car", "source": "tracktitan", "trackMatched": True, "carMatched": False},
    ]


def test_finish_event_unmatched_is_none_when_everything_matched(mm, mocker):
    manager, dm, dbx, tmp = mm
    setup = _setup(id="id1", ts=2000)
    _pages(dm, [setup])
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])
    events = []
    manager.on_progress = events.append

    manager.run()

    finish = next(e for e in events if e.kind == ProgressKind.FINISH)
    assert finish.unmatched is None


def test_a_shared_unmatched_tracker_can_be_injected(mocker, tmp_path):
    from orchestration.master_manager import MasterManager
    from domain.unmatched import UnmatchedTracker

    mocker.patch("orchestration.master_manager.DOWNLOAD_PATH", tmp_path)
    dm = MagicMock()
    dbx = MagicMock()
    dbx.list_setups.return_value = []
    car_manager = MagicMock()
    car_manager.get_car_name.side_effect = lambda car: None
    track_manager = MagicMock()
    track_manager.get_official_track_name.side_effect = lambda track: track
    tracker = UnmatchedTracker()

    manager = MasterManager(
        download_manager=dm, dropbox_client=dbx, workers=1,
        car_manager=car_manager, track_manager=track_manager, unmatched=tracker,
    )
    dm.get_setups_list.side_effect = [[_setup(id="id1", ts=2000)], []]

    manager.run()

    assert manager.unmatched is tracker
    assert tracker.serialize() == [
        {"track": "Spa", "car": "Porsche 963", "source": "tracktitan", "trackMatched": True, "carMatched": False},
    ]


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


def test_upload_publishes_under_the_officialized_car_and_track_names(mm, mocker):
    """mapping.json's `name` wins over the raw TrackTitan catalog text - e.g. a
    raw "Oreca 07 Gibson 2024 (ELMS)" catalog car must publish under Dropbox's
    "Oreca 07 (ELMS)" folder, not its own sanitized raw text."""
    manager, dm, dbx, tmp = mm
    manager.car_manager.get_car_name.side_effect = lambda car: "Oreca 07 (ELMS)"
    manager.track_manager.get_official_track_name.side_effect = lambda track: "Spa"
    setup = _setup(id="id1", ts=2000, car="Oreca 07 Gibson 2024 (ELMS)")
    _pages(dm, [setup])
    _downloadable(dm, tmp)
    _fake_extraction(mocker, [_svm(tmp)])

    manager.run()

    manager.car_manager.get_car_name.assert_called_once_with("Oreca 07 Gibson 2024 (ELMS)")
    manager.track_manager.get_official_track_name.assert_called_once_with("Spa")
    dbx.upload.assert_called_once()
    _, name_arg = dbx.upload.call_args[0]
    assert name_arg == "Oreca 07 (ELMS)/Spa/" + setup.remote_filename
    assert "Gibson" not in name_arg


def test_relocate_target_uses_the_officialized_car_and_track_names(mm):
    manager, dm, dbx, tmp = mm
    manager.car_manager.get_car_name.side_effect = lambda car: "Oreca 07 (ELMS)"
    dbx.list_setups.return_value = [
        _remote("Oreca 07 Gibson 2024 (ELMS)/Spa/HYMO-Spa_Oreca_07_Gibson_2024__ELMS__id1_1000.zip", "id1", 1000)
    ]
    _pages(dm, [_setup(id="id1", ts=1000, car="Oreca 07 Gibson 2024 (ELMS)")])

    manager.run()

    dbx.move.assert_called_once()
    _, target = dbx.move.call_args[0]
    assert target.startswith("/lmu-setups/Oreca 07 (ELMS)/Spa/")


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
