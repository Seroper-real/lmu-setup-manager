"""Drives the real main.run_full / run_master / run_slave through the sandbox with a
recording on_progress callback, and checks that a mid-run cancel_event truncates work.

This is the GUI's progress bridge (src/gui/api.py Api.start_download) exercised at the
level it actually depends on: main.run_*(log, on_progress=..., cancel_event=...) and
the managers they build.
"""
import logging
import threading

import pytest

from sandbox_harness import REPO_FIXTURES, Sandbox, make_setup


@pytest.fixture
def log() -> logging.Logger:
    return logging.getLogger("TrackTitanDownloader")


def _wire_main_seams(mocker, box: Sandbox, repo_fixtures) -> None:
    """Seams only main.py's call path touches: the clients.build_* factories and the
    config attributes main.run_full/_require_lmu_path read. Mirrors the `wired`
    fixture in test_sandbox_main_wiring.py."""
    mocker.patch("clients.protocols.MOCK_TRACKTITAN", True)
    mocker.patch("clients.protocols.MOCK_DROPBOX", True)
    mocker.patch("clients.mocks.mock_track_titan_client.SANDBOX_TRACKTITAN_PATH", repo_fixtures)
    mocker.patch("clients.mocks.mock_dropbox_client.SANDBOX_DROPBOX_PATH", box.share)

    mocker.patch("core.config.LMU_SETUPS_BASE_PATH", box.lmu)
    mocker.patch("processing.setup_manager.LMU_SETUPS_BASE_PATH", box.lmu)
    mocker.patch("domain.setup_db.DB_PATH", box.root / "sandbox.db")
    mocker.patch("core.config.SANDBOX_ENABLED", True)
    mocker.patch("core.config.MOCK_TRACKTITAN", True)
    mocker.patch("core.config.MOCK_DROPBOX", True)
    mocker.patch("core.config.MOCK_LMU", True)

    # Guard rails: a real client must never be constructed in this test.
    mocker.patch("clients.track_titan_client.TrackTitanClient")
    mocker.patch("clients.dropbox_client.DropboxClient")


def _wire_orchestration_seams(mocker, box: Sandbox) -> None:
    """What tests/integration/conftest.py's `sandbox` fixture does, replicated so a
    manually-built (non-fixture) Sandbox instance can be wired the same way - needed
    here because the cancellation test needs two independent boxes in one test."""
    from config_profiles import build_config

    cfg = build_config()
    setups_cfg = cfg["paths"]["setups"]
    clean_download = cfg["paths"]["download"]["clean_download_after_copy"]
    extensions = {e.lower() for e in setups_cfg["file_extensions"]}

    for module in (
        "orchestration.download_manager",
        "orchestration.master_manager",
        "orchestration.slave_manager",
        "processing.setup_manager",
    ):
        mocker.patch(f"{module}.DOWNLOAD_PATH", box.downloads)

    mocker.patch("orchestration.master_manager.CLEAN_DOWNLOAD", clean_download)
    mocker.patch("orchestration.master_manager.SETUP_FILE_EXTENSIONS", extensions)
    mocker.patch("processing.setup_manager.CLEAN_DOWNLOAD", clean_download)
    mocker.patch("processing.setup_manager.OVERWRITE", setups_cfg["overwrite"])
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", setups_cfg["delete_previous_version"])
    mocker.patch("processing.setup_manager.SETUP_FILE_EXTENSIONS", extensions)
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", cfg["remote_mappings"]["enabled"])
    mocker.patch("processing.track_manager.get_path", return_value=box.tracks_file)
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", cfg["remote_mappings"]["enabled"])
    mocker.patch("processing.car_manager.get_path", return_value=box.tracks_file)


def _wire_all(mocker, box: Sandbox, repo_fixtures) -> None:
    box.set_tracks([("spa", "Spa"), ("monza", "Monza")])
    # Two cars so at least two of the shipped fixture catalog's setups
    # actually match both track and car (Porsche 963/Spa - WEC, Genesis
    # GMR-001/Monza) - test_cancel_event_mid_run_yields_strictly_fewer_
    # installed_files needs >= 2 installed setups to observe a mid-run cancel.
    box.set_cars([("963", "Porsche 963"), ("genesis", "Genesis GMR-001")])
    _wire_orchestration_seams(mocker, box)
    _wire_main_seams(mocker, box, repo_fixtures)


def test_run_full_reports_start_and_install_for_every_installed_setup(sandbox, repo_fixtures, mocker, log):
    _wire_all(mocker, sandbox, repo_fixtures)
    import main

    events = []
    main.run_full(log, on_progress=events.append)

    kinds = [e.kind for e in events]
    assert kinds.count("start") >= 1
    assert kinds.count("install") >= 1
    # The checked-in fixture catalog's "Season Bundle" entry must never be installed.
    assert not any("Season Bundle" in (e.title or "") for e in events if e.kind == "install")
    # Everything actually landed on disk, exactly as the no-instrumentation run does.
    assert len(sandbox.installed_files()) >= 1


def test_run_full_without_a_callback_still_runs_to_completion(sandbox, repo_fixtures, mocker, log):
    """on_progress/cancel_event are optional, not a back-compat requirement - omitting
    both must behave exactly like calling run_full(log) today."""
    _wire_all(mocker, sandbox, repo_fixtures)
    import main

    main.run_full(log)

    assert len(sandbox.installed_files()) >= 1


def test_cancel_event_mid_run_yields_strictly_fewer_installed_files(tmp_path_factory, mocker, log):
    import main

    box_full = Sandbox(tmp_path_factory.mktemp("uninterrupted"))
    _wire_all(mocker, box_full, REPO_FIXTURES)
    main.run_full(log)
    uninterrupted_count = len(box_full.installed_files())
    assert uninterrupted_count > 1, "need at least 2 installed setups for cancellation to be observable"

    box_cancelled = Sandbox(tmp_path_factory.mktemp("cancelled"))
    _wire_all(mocker, box_cancelled, REPO_FIXTURES)
    cancel_event = threading.Event()
    installs = {"count": 0}

    def on_progress(event):
        if event.kind == "install":
            installs["count"] += 1
            if installs["count"] == 1:
                cancel_event.set()

    main.run_full(log, on_progress=on_progress, cancel_event=cancel_event)
    cancelled_count = len(box_cancelled.installed_files())

    assert cancelled_count < uninterrupted_count


def test_cancel_event_emits_a_stopped_event(tmp_path_factory, mocker, log):
    import main

    box = Sandbox(tmp_path_factory.mktemp("stopped-event"))
    _wire_all(mocker, box, REPO_FIXTURES)
    cancel_event = threading.Event()
    events = []

    def on_progress(event):
        events.append(event)
        if event.kind == "install":
            cancel_event.set()

    main.run_full(log, on_progress=on_progress, cancel_event=cancel_event)

    assert any(e.kind == "stopped" for e in events)


def test_run_full_does_not_install_a_setup_twice_when_a_page_repeats_its_id(sandbox, repo_fixtures, mocker, log):
    """The TrackTitan API can hand the same setup id back on two adjacent pages
    (a known pagination overlap - see MasterManager._dispatch's own guard for
    the same issue on the master-mode side). run_full must download/install
    it only once, not once per page it appears on."""
    _wire_all(mocker, sandbox, repo_fixtures)
    # Use a synthetic per-test catalog (instead of the checked-in repo fixture
    # _wire_main_seams points at) so a duplicate id can be crafted deliberately,
    # and force one setup per page so the duplicate straddles a page boundary.
    mocker.patch("clients.mocks.mock_track_titan_client.SANDBOX_TRACKTITAN_PATH", sandbox.catalog_dir)
    mocker.patch("orchestration.download_manager.PAGE_SIZE", 1)

    dup = make_setup("dup-id", "Spa", car="Porsche 963")
    sandbox.write_catalog([dup, dup])
    sandbox.add_archive("dup-id", {"setup.svm": "content"})

    import main

    events = []
    main.run_full(log, on_progress=events.append)

    assert sum(1 for e in events if e.kind == "install") == 1
    assert sum(1 for e in events if e.kind == "start") == 1


def test_run_master_and_run_slave_accept_progress_kwargs(sandbox, repo_fixtures, mocker, log):
    _wire_all(mocker, sandbox, repo_fixtures)
    import main

    master_events = []
    main.run_master(log, on_progress=master_events.append)
    assert len(sandbox.share_names()) >= 1

    slave_events = []
    main.run_slave(log, on_progress=slave_events.append)
    assert len(sandbox.installed_files()) >= 1
