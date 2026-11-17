"""DUAL mode (master + local install): publish to the share AND install locally.
Drives the real DualManager through the sandbox; only the three external
systems are mocked."""
import zipfile

import pytest

from sandbox_harness import make_setup

SID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
SID2 = "aaaaaaaa-bbbb-4ccc-8ddd-000000000002"
V1 = 1700000000
V2 = 1700009999


@pytest.fixture(autouse=True)
def _world(sandbox):
    sandbox.set_tracks([("spa", "Spa"), ("monza", "Monza")])
    sandbox.set_cars([("963", "Porsche 963"), ("oreca", "Oreca 07")])


def _one(sandbox, ts=V1, member="q_v1.svm", sid=SID, track="Spa", car="Porsche 963"):
    sandbox.write_catalog([make_setup(sid, track, car=car, ts=ts)])
    sandbox.add_archive(sid, {member: member})


def _name(ts, sid=SID):
    return f"HYMO-Spa_Porsche_963_{sid}_{ts}.zip"


@pytest.fixture
def dbx_download(mocker):
    from clients.mocks.mock_dropbox_client import MockDropboxClient
    return mocker.spy(MockDropboxClient, "download_to")


@pytest.fixture
def tt_download(mocker):
    from clients.mocks.mock_track_titan_client import MockTrackTitanClient
    return mocker.spy(MockTrackTitanClient, "download_link")


def test_publishes_and_installs_without_any_dropbox_download(sandbox, in_memory_db, dbx_download):
    _one(sandbox)

    sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == {_name(V1)}
    assert sandbox.installed_files() == {"Spa/q_v1.svm"}
    dbx_download.assert_not_called()
    row = in_memory_db.fetch_installed_setup(SID)
    assert row is not None
    assert row.track == "Spa" and row.car == "Porsche 963"


def test_counters(sandbox, in_memory_db):
    _one(sandbox)
    m = sandbox.run_dual(in_memory_db)
    assert m.installed_count == 1
    assert m.install_failed_count == 0


def test_bundle_is_skipped(sandbox, in_memory_db):
    sandbox.write_catalog([make_setup(SID, "Spa", ts=V1, is_bundle=True)])
    sandbox.add_archive(SID, {"b.svm": "b"})

    sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == set()
    assert sandbox.installed_files() == set()
    assert in_memory_db.fetch_installed_setup(SID) is None


def test_unmatched_track_and_car_are_skipped_in_both_halves(sandbox, in_memory_db):
    sandbox.write_catalog([
        make_setup(SID, "Nowhere Ring", ts=V1),
        make_setup(SID2, "Spa", car="Mystery Car", ts=V1),
    ])
    sandbox.add_archive(SID, {"a.svm": "a"})
    sandbox.add_archive(SID2, {"b.svm": "b"})

    sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == set()
    assert sandbox.installed_files() == set()
    assert in_memory_db.fetch_all_installed_setups() == []


def test_car_filter_unselected_neither_uploaded_nor_installed(sandbox, in_memory_db, tt_download):
    from core import settings_db
    settings_db.save_config({"cars": {"all": False, "selected": ["Porsche 963"]}})
    sandbox.write_catalog([
        make_setup(SID, "Spa", car="Porsche 963", ts=V1),
        make_setup(SID2, "Spa", car="Oreca 07", ts=V1),
    ])
    sandbox.add_archive(SID, {"p.svm": "p"})
    sandbox.add_archive(SID2, {"o.svm": "o"})

    sandbox.run_dual(in_memory_db)

    assert {n.split("_")[-2] for n in sandbox.share_names()} == {SID}
    assert sandbox.installed_files() == {"Spa/p.svm"}
    assert in_memory_db.fetch_installed_setup(SID2) is None
    assert {c.args[1] for c in tt_download.call_args_list} == {SID}


def test_version_bump_reuploads_deletes_old_zip_and_reinstalls(sandbox, in_memory_db):
    _one(sandbox)
    sandbox.run_dual(in_memory_db)

    _one(sandbox, ts=V2, member="q_v2.svm")
    sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == {_name(V2)}
    assert sandbox.installed_files() == {"Spa/q_v2.svm"}
    assert in_memory_db.is_installed_last_version(SID, V2)


def test_old_zip_kept_when_new_upload_fails(sandbox, in_memory_db, mocker):
    _one(sandbox)
    sandbox.run_dual(in_memory_db)
    _one(sandbox, ts=V2, member="q_v2.svm")

    from clients.mocks.mock_dropbox_client import MockDropboxClient
    mocker.patch.object(MockDropboxClient, "upload", side_effect=RuntimeError("boom"))

    sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == {_name(V1)}


def test_second_run_is_a_noop(sandbox, in_memory_db, mocker, tt_download):
    _one(sandbox)
    sandbox.run_dual(in_memory_db)

    from clients.mocks.mock_dropbox_client import MockDropboxClient
    from processing.setup_manager import SetupManager
    upload = mocker.spy(MockDropboxClient, "upload")
    install = mocker.spy(SetupManager, "install_setup")
    tt_download.reset_mock()

    m = sandbox.run_dual(in_memory_db)

    upload.assert_not_called()
    install.assert_not_called()
    tt_download.assert_not_called()
    assert m.installed_count == 0


def test_share_current_but_not_installed_installs_from_share_without_tracktitan(
    sandbox, in_memory_db, tt_download, dbx_download, mocker,
):
    _one(sandbox)
    sandbox.run_master()  # share filled, nothing installed locally
    assert sandbox.installed_files() == set()
    tt_download.reset_mock()

    from clients.mocks.mock_dropbox_client import MockDropboxClient
    upload = mocker.spy(MockDropboxClient, "upload")

    sandbox.run_dual(in_memory_db)

    tt_download.assert_not_called()
    upload.assert_not_called()
    assert dbx_download.call_count == 1
    assert sandbox.installed_files() == {"Spa/q_v1.svm"}
    assert in_memory_db.is_installed_last_version(SID, V1)


def test_install_failure_does_not_stop_upload(sandbox, in_memory_db, mocker):
    _one(sandbox)
    from processing.setup_manager import SetupManager
    mocker.patch.object(SetupManager, "install_setup", side_effect=RuntimeError("disk full"))

    m = sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == {_name(V1)}
    assert sandbox.installed_files() == set()
    assert m.install_failed_count == 1 and m.installed_count == 0


def test_install_returning_false_counts_as_failed_but_uploads(sandbox, in_memory_db, mocker):
    _one(sandbox)
    from processing.setup_manager import SetupManager
    mocker.patch.object(SetupManager, "install_setup", return_value=False)

    m = sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == {_name(V1)}
    assert m.install_failed_count == 1


def test_upload_failure_does_not_stop_install(sandbox, in_memory_db, mocker):
    _one(sandbox)
    from clients.mocks.mock_dropbox_client import MockDropboxClient
    mocker.patch.object(MockDropboxClient, "upload", side_effect=RuntimeError("quota"))

    m = sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == set()
    assert sandbox.installed_files() == {"Spa/q_v1.svm"}
    assert in_memory_db.is_installed_last_version(SID, V1)
    assert m.installed_count == 1


def test_published_package_is_intact_after_the_local_install(sandbox, in_memory_db):
    _one(sandbox)
    sandbox.run_dual(in_memory_db)

    pkg = next(sandbox.share.glob("**/*.zip"))
    with zipfile.ZipFile(pkg) as zf:
        assert "q_v1.svm" in zf.namelist()
        assert ".metadata.json" in zf.namelist()


def test_auth_error_from_share_download_is_reraised(sandbox, in_memory_db, mocker):
    from core.errors import AuthError
    _one(sandbox)
    sandbox.run_master()
    from clients.mocks.mock_dropbox_client import MockDropboxClient
    mocker.patch.object(MockDropboxClient, "download_to", side_effect=AuthError("expired", code="dropbox"))

    with pytest.raises(AuthError):
        sandbox.run_dual(in_memory_db)


def test_non_auth_share_download_error_is_isolated(sandbox, in_memory_db, mocker):
    _one(sandbox)
    sandbox.run_master()
    from clients.mocks.mock_dropbox_client import MockDropboxClient
    mocker.patch.object(MockDropboxClient, "download_to", side_effect=RuntimeError("net"))

    m = sandbox.run_dual(in_memory_db)

    assert m.install_failed_count == 1
    assert sandbox.installed_files() == set()


def test_install_event_emitted_once_per_setup(sandbox, in_memory_db):
    from core.progress import ProgressKind
    from orchestration.download_manager import DownloadManager
    from orchestration.dual_manager import DualManager
    _one(sandbox)
    events = []
    DualManager(
        download_manager=DownloadManager(database=None, client=sandbox.tracktitan()),
        dropbox_client=sandbox.dropbox(),
        setup_manager=sandbox.setup_manager(in_memory_db),
        database=in_memory_db,
        on_progress=events.append,
    ).run()

    assert [e.kind for e in events].count(ProgressKind.INSTALL) == 1


def test_failed_install_leaves_no_staged_copy_or_extraction_behind(sandbox, in_memory_db, mocker):
    _one(sandbox)
    from processing.setup_manager import SetupManager

    def _explode(self, downloaded_path, setup, **kwargs):
        # Simulate a crash midway through extraction.
        (sandbox.downloads / setup.id).mkdir(parents=True, exist_ok=True)
        raise RuntimeError("corrupt archive")

    mocker.patch.object(SetupManager, "install_setup", _explode)

    sandbox.run_dual(in_memory_db)

    assert sandbox.share_names() == {_name(V1)}
    assert list(sandbox.downloads.iterdir()) == []


def test_install_rewriting_safe_names_does_not_move_the_upload(sandbox, in_memory_db, mocker):
    _one(sandbox)
    from processing.setup_manager import SetupManager
    real_install = SetupManager.install_setup

    def _install_and_scribble(self, downloaded_path, setup, **kwargs):
        result = real_install(self, downloaded_path, setup, **kwargs)
        setup.safe_car = "Scribbled Car"
        setup.safe_track = "Scribbled Track"
        return result

    mocker.patch.object(SetupManager, "install_setup", _install_and_scribble)

    sandbox.run_dual(in_memory_db)

    pkg = next(sandbox.share.glob("**/*.zip"))
    assert pkg.relative_to(sandbox.share).parts[:2] == ("Porsche 963", "Spa")
    assert sandbox.installed_files() == {"Spa/q_v1.svm"}


def test_cancel_stops_both_halves_for_later_setups(sandbox, in_memory_db):
    import threading
    from core.progress import ProgressKind
    from orchestration.download_manager import DownloadManager
    from orchestration.dual_manager import DualManager

    sandbox.write_catalog([
        make_setup(SID, "Spa", car="Porsche 963", ts=V1),
        make_setup(SID2, "Monza", car="Porsche 963", ts=V1),
    ])
    sandbox.add_archive(SID, {"q_v1.svm": "q_v1.svm"})
    sandbox.add_archive(SID2, {"m_v1.svm": "m_v1.svm"})
    cancel = threading.Event()
    events = []

    def _on_progress(event):
        events.append(event)
        # Stop as soon as the first setup starts: it still completes, the second never begins.
        if event.kind == ProgressKind.START:
            cancel.set()

    manager = DualManager(
        download_manager=DownloadManager(database=None, client=sandbox.tracktitan(), cancel_event=cancel),
        dropbox_client=sandbox.dropbox(),
        setup_manager=sandbox.setup_manager(in_memory_db),
        database=in_memory_db,
        on_progress=_on_progress,
        cancel_event=cancel,
    )
    manager.run()

    assert len(sandbox.share_names()) == 1
    assert len(sandbox.installed_files()) == 1
    assert manager.installed_count == 1
    assert events[-1].kind == ProgressKind.STOPPED
