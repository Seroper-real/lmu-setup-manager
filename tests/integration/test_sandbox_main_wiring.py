"""Drives main.run_full / run_master / run_slave, the way the app actually starts.

Covers what the other integration tests bypass: the clients.build_* factories picking
the mocks off the MOCK_* flags, and SetupManager falling back to the (patched) config
LMU path. There is no headless LMU-path gate left in main.py to cover here (GUI-only:
run_full never validates LMU_SETUPS_BASE_PATH itself, that check now lives in the
GUI's own pre-flight, surfaced via Api.get_bootstrap()'s "lmuPathExists" and covered in
tests/unit/test_gui_api.py).

main.py no longer imports config at module scope — every helper re-reads it at call
time — so the seams patched here are the `config`/`clients` module attributes, which
is a more truthful reflection of what config.py produces when MOCK_LMU is on.
"""
import logging

import pytest


@pytest.fixture
def wired(sandbox, repo_fixtures, tmp_path, mocker):
    """Point every module-level seam at the sandbox, as config.py would with all MOCK_* on."""
    sandbox.set_tracks([("spa", "Spa"), ("monza", "Monza")])

    # The factories read these names, imported into the clients namespace.
    mocker.patch("clients.protocols.MOCK_TRACKTITAN", True)
    mocker.patch("clients.protocols.MOCK_DROPBOX", True)
    # The mock clients resolve their roots from config at construction time.
    mocker.patch("clients.mocks.mock_track_titan_client.SANDBOX_TRACKTITAN_PATH", repo_fixtures)
    mocker.patch("clients.mocks.mock_dropbox_client.SANDBOX_DROPBOX_PATH", sandbox.share)

    # What config.py does when MOCK_LMU is on. _require_lmu_path and _log_sandbox
    # both `from config import ...` at call time, so patch the config attributes.
    mocker.patch("core.config.LMU_SETUPS_BASE_PATH", sandbox.lmu)
    mocker.patch("processing.setup_manager.LMU_SETUPS_BASE_PATH", sandbox.lmu)
    mocker.patch("domain.setup_db.DB_PATH", tmp_path / "sandbox.db")
    mocker.patch("core.config.SANDBOX_ENABLED", True)
    mocker.patch("core.config.MOCK_TRACKTITAN", True)
    mocker.patch("core.config.MOCK_DROPBOX", True)
    mocker.patch("core.config.MOCK_LMU", True)

    real_tt = mocker.patch("clients.track_titan_client.TrackTitanClient")
    real_dbx = mocker.patch("clients.dropbox_client.DropboxClient")
    return sandbox, real_tt, real_dbx


@pytest.fixture
def log():
    return logging.getLogger("TrackTitanDownloader")


EXPECTED_INSTALL = {
    "Spa/Spa_Porsche963_Quali.svm",
    "Monza/Monza_Cadillac_Race.svm",
    "Nordschleife-HYMO/Nordschleife_Ferrari499P.svm",
}


def test_run_master_publishes_through_the_factories(wired, log):
    import main

    box, real_tt, real_dbx = wired
    main.run_master(log)

    assert len(box.share_names()) >= 3
    real_tt.assert_not_called()
    real_dbx.assert_not_called()


def test_run_slave_installs_through_the_factories(wired, log):
    import main

    box, real_tt, real_dbx = wired
    main.run_master(log)
    main.run_slave(log)

    assert EXPECTED_INSTALL <= box.installed_files()
    real_tt.assert_not_called()
    real_dbx.assert_not_called()


def test_run_full_installs_without_tokens_or_a_game_install(wired, log):
    import main

    box, real_tt, real_dbx = wired
    main.run_full(log)

    assert EXPECTED_INSTALL <= box.installed_files()
    real_tt.assert_not_called()
    # FULL never touches Dropbox.
    real_dbx.assert_not_called()


def test_run_full_is_idempotent(wired, log):
    import main

    box, _, _ = wired
    main.run_full(log)
    main.run_full(log)

    assert EXPECTED_INSTALL <= box.installed_files()


