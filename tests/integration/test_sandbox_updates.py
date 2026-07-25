"""Version bumps across the whole chain: TrackTitan -> share -> game folder.

The share must hold exactly one zip per setup id, and the game folder exactly one
generation of .svm files. Both are driven end to end through the sandbox.
"""
import pytest

from sandbox_harness import make_setup

SETUP_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
V1_TS = 1700000000
V2_TS = 1700009999


@pytest.fixture(autouse=True)
def _tracks(sandbox):
    sandbox.set_tracks([("spa", "Spa")])


def _publish_v1(sandbox):
    sandbox.write_catalog([make_setup(SETUP_ID, "Spa", ts=V1_TS)])
    sandbox.add_archive(SETUP_ID, {"quali_v1.svm": "v1"})
    sandbox.run_master()


def _publish_v2(sandbox):
    sandbox.write_catalog([make_setup(SETUP_ID, "Spa", ts=V2_TS)])
    sandbox.add_archive(SETUP_ID, {"quali_v2.svm": "v2"})
    sandbox.run_master()


def test_master_replaces_the_stale_zip_on_the_share(sandbox):
    _publish_v1(sandbox)
    assert sandbox.share_names() == {f"HYMO-Spa_Porsche_963_{SETUP_ID}_{V1_TS}.zip"}

    _publish_v2(sandbox)
    assert sandbox.share_names() == {f"HYMO-Spa_Porsche_963_{SETUP_ID}_{V2_TS}.zip"}, \
        "the previous version must be deleted after the new upload succeeds"


def test_master_does_not_reupload_an_unchanged_setup(sandbox, mocker):
    _publish_v1(sandbox)

    from clients.mocks.mock_dropbox_client import MockDropboxClient
    upload = mocker.spy(MockDropboxClient, "upload")

    sandbox.run_master()

    upload.assert_not_called()


def test_master_skips_when_share_is_newer_than_the_api(sandbox, mocker):
    _publish_v2(sandbox)

    # The API rolls back to an older timestamp; the share must win.
    sandbox.write_catalog([make_setup(SETUP_ID, "Spa", ts=V1_TS)])

    from clients.mocks.mock_dropbox_client import MockDropboxClient
    upload = mocker.spy(MockDropboxClient, "upload")
    delete = mocker.spy(MockDropboxClient, "delete")

    sandbox.run_master()

    upload.assert_not_called()
    delete.assert_not_called()
    assert sandbox.share_names() == {f"HYMO-Spa_Porsche_963_{SETUP_ID}_{V2_TS}.zip"}


def test_slave_upgrades_an_installed_setup_and_drops_the_old_file(sandbox, in_memory_db):
    _publish_v1(sandbox)
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/quali_v1.svm"}

    _publish_v2(sandbox)
    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Spa/quali_v2.svm"}, \
        "the superseded .svm must be removed from the game folder"
    assert in_memory_db.is_installed_last_version(SETUP_ID, V2_TS) is True


def test_slave_keeps_a_file_that_survives_the_new_version(sandbox, in_memory_db):
    """_cleanup_old must not delete a name the new version also ships."""
    sandbox.write_catalog([make_setup(SETUP_ID, "Spa", ts=V1_TS)])
    sandbox.add_archive(SETUP_ID, {"shared.svm": "v1", "gone.svm": "v1"})
    sandbox.run_master()
    sandbox.run_slave(in_memory_db)
    assert sandbox.installed_files() == {"Spa/shared.svm", "Spa/gone.svm"}

    sandbox.write_catalog([make_setup(SETUP_ID, "Spa", ts=V2_TS)])
    sandbox.add_archive(SETUP_ID, {"shared.svm": "v2"})
    sandbox.run_master()
    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Spa/shared.svm"}
    assert (sandbox.lmu / "Spa" / "shared.svm").read_text() == "v2", "must be overwritten, not skipped"


def test_slave_ignores_a_non_conforming_zip_on_the_share(sandbox, in_memory_db):
    _publish_v1(sandbox)
    (sandbox.share / "manually-dropped.zip").write_bytes(b"not a package")

    sandbox.run_slave(in_memory_db)

    assert sandbox.installed_files() == {"Spa/quali_v1.svm"}


def test_master_relocates_a_legacy_flat_layout_zip_without_republishing(sandbox, mocker):
    """A zip already published under the old <car>/<file>.zip layout (predating
    the unified <car>/<track>/<file>.zip share tree) must be moved into place on
    the next master run, without a fresh TrackTitan download."""
    name = f"HYMO-Spa_Porsche_963_{SETUP_ID}_{V1_TS}.zip"
    legacy_path = sandbox.share / "Porsche_963" / name
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_bytes(b"legacy package bytes")

    sandbox.write_catalog([make_setup(SETUP_ID, "Spa", ts=V1_TS)])

    from clients.mocks.mock_track_titan_client import MockTrackTitanClient
    download = mocker.spy(MockTrackTitanClient, "download")

    sandbox.run_master()

    assert not legacy_path.exists()
    assert (sandbox.share / "Porsche 963" / "Spa" / name).is_file()
    download.assert_not_called()
