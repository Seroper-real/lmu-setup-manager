from pathlib import Path

import pytest

from config_profiles import build_config
from sandbox_harness import REPO_FIXTURES, Sandbox


@pytest.fixture
def repo_fixtures() -> Path:
    """The catalog shipped in sandbox/tracktitan/, as opposed to a synthetic one."""
    return REPO_FIXTURES


@pytest.fixture
def sandbox(tmp_path, mocker) -> Sandbox:
    """A disposable app root wired to tests/resources/config.test.json.

    The managers read these as module-level constants, so they are patched in place
    rather than re-imported. Values come from the test profile, never from literals
    duplicated here and never from the repo's own config/config.json.
    """
    box = Sandbox(tmp_path)
    cfg = build_config()

    setups = cfg["paths"]["setups"]
    clean_download = cfg["paths"]["download"]["clean_download_after_copy"]
    extensions = {e.lower() for e in setups["file_extensions"]}

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
    mocker.patch("processing.setup_manager.OVERWRITE", setups["overwrite"])
    mocker.patch("processing.setup_manager.DELETE_PREVIOUS_VERSION", setups["delete_previous_version"])
    mocker.patch("processing.setup_manager.SETUP_FILE_EXTENSIONS", extensions)

    # No network: never fetch the remote tracks.json, and read ours instead.
    mocker.patch("processing.track_manager.REMOTE_TRACKS_ENABLED", cfg["remote_tracks"]["enabled"])
    mocker.patch("processing.track_manager.get_path", return_value=box.tracks_file)

    return box
