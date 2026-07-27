"""Publish -> install round trip over the fixtures actually shipped in sandbox/.

This is the test that guards the sandbox assets themselves: if someone edits
sandbox/tracktitan/, these expectations must still hold. The shipped catalog also
carries extra entries covering every real TrackTitan track/car name for manual
--sandbox exploration, so assertions here check the four curated ids/files are
still present rather than pinning the catalog to an exact size.
"""
import json
import zipfile

import pytest

SPA_ID = "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
UNMAPPED_ID = "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e"
BUNDLE_ID = "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f"
NESTED_ID = "3d4e5f6a-7b8c-4d9e-8f0a-2b3c4d5e6f70"


@pytest.fixture(autouse=True)
def _tracks(sandbox):
    sandbox.set_tracks([("spa", "Spa"), ("monza", "Monza")])


def test_master_publishes_every_non_bundle_setup_with_svm_plus_metadata(sandbox, repo_fixtures):
    from core.archive import METADATA_FILENAME

    dbx = sandbox.run_master(base_path=repo_fixtures)

    published = {r.setup_id: r for r in dbx.list_setups()}
    assert {SPA_ID, UNMAPPED_ID, NESTED_ID} <= set(published)
    assert BUNDLE_ID not in published, "bundles must never be published"

    # The catalog's raw track text is "Spa - WEC" - officialized against
    # mapping.json to plain "Spa", not published verbatim.
    assert published[SPA_ID].name == f"HYMO-Spa_Porsche_963_{SPA_ID}_1700000000.zip"
    assert list(sandbox.downloads.iterdir()) == [], "master must clean its temp files"

    nested = published[NESTED_ID]
    with zipfile.ZipFile(nested.path_lower) as zf:
        names = set(zf.namelist())
        metadata = json.loads(zf.read(METADATA_FILENAME))

    # The nested inner.zip was recursed into, and readme.txt filtered out.
    assert names == {"Monza_Cadillac_Race.svm", METADATA_FILENAME}
    assert metadata["id"] == NESTED_ID


def test_slave_installs_published_setups_into_mock_lmu_and_a_second_run_is_a_no_op(
    sandbox, in_memory_db, mocker, repo_fixtures,
):
    sandbox.run_master(base_path=repo_fixtures)
    sandbox.run_slave(in_memory_db)

    assert {
        "Spa/Spa_Porsche963_Quali.svm",
        "Monza/Monza_Cadillac_Race.svm",
        # Unmapped track lands in the -HYMO fallback folder.
        "Nordschleife-HYMO/Nordschleife_Ferrari499P.svm",
    } <= sandbox.installed_files()

    assert in_memory_db.is_installed_last_version(SPA_ID, 1700000000) is True
    assert in_memory_db.is_track_found(SPA_ID) is True
    assert in_memory_db.is_track_found(UNMAPPED_ID) is False

    from clients.mocks.mock_dropbox_client import MockDropboxClient
    spy = mocker.spy(MockDropboxClient, "download_to")

    sandbox.run_slave(in_memory_db)

    spy.assert_not_called()
