"""Regression: dual (and master) mode lost the downloaded archive.

DownloadManager.already_downloaded holds *ids* sliced from every .zip in
DOWNLOAD_PATH, and download() used to trust it without checking that the
HYMO-<track>-<id>.zip it hands back exists. Leftovers stored under another track
segment (a FULL run's raw TrackTitan track name) or a dual-<id>.zip staging copy
therefore made the publish/stage steps fail with "file not found".

These tests run the whole checked-in mock catalog (several pages) with the real
mapping.json, plant such leftovers BEFORE the DownloadManager is built, and
require zero failures and the same counts as clean master-only / full-only runs.
"""
import json
import logging
import shutil
import sqlite3

import pytest

from sandbox_harness import REPO_FIXTURES

REPO_ROOT = REPO_FIXTURES.parents[1]
EXPECTED = 34  # matched, non-bundle setups in the shipped catalog


@pytest.fixture(autouse=True)
def _production_catalog(sandbox, mocker):
    """Real mapping.json (all tracks/cars), the real checked-in catalog, and a
    small page size so the catalog spans several pages."""
    shutil.copy(REPO_ROOT / "config" / "mapping.json", sandbox.tracks_file)
    sandbox.catalog_dir = REPO_FIXTURES
    mocker.patch("orchestration.download_manager.PAGE_SIZE", 7)


def _catalog():
    return json.loads((REPO_FIXTURES / "catalog.json").read_text(encoding="utf-8"))["data"]["setups"]


def _wipe(sandbox):
    for d in (sandbox.downloads, sandbox.share, sandbox.lmu):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)


def _patch_clean(mocker, value):
    for m in ("orchestration.master_manager", "orchestration.dual_manager", "processing.setup_manager"):
        mocker.patch(f"{m}.CLEAN_DOWNLOAD", value)


def _fresh_db():
    from domain.setup_db import SetupDb

    class _Db(SetupDb):
        def __init__(self):
            self.conn = sqlite3.connect(":memory:")
            self.create_tables()
    return _Db()


def _plant_full_style(sandbox, ids=None):
    """What a FULL run leaves: HYMO-<raw track>-<id>.zip for every non-bundle."""
    from domain.setup import Setup
    planted = 0
    for data in _catalog():
        s = Setup(data)
        if s.is_bundle or (ids is not None and s.id not in ids):
            continue
        src = next((REPO_FIXTURES / "setups" / n for n in (f"{s.id}-SANDBOX.zip", f"{s.id}.zip")
                    if (REPO_FIXTURES / "setups" / n).exists()), None)
        if src is None:
            continue
        shutil.copy(src, sandbox.downloads / f"HYMO-{s.safe_track}-{s.id}.zip")
        planted += 1
    return planted


def _plant_staging(sandbox, ids=None):
    """dual-<id>.zip staging leftovers (never a valid TrackTitan archive here)."""
    from domain.setup import Setup
    for data in _catalog():
        sid = Setup(data).id
        if ids is None or sid in ids:
            (sandbox.downloads / f"dual-{sid}.zip").write_bytes(b"not a real archive")


def _failures(caplog):
    return [r.getMessage() for r in caplog.records if "Failed" in r.getMessage()]


def _leftover_archives(sandbox):
    return sorted(p.name for p in sandbox.downloads.glob("*.zip") if p.name.startswith(("dual-", "HYMO-")))


def _baseline(sandbox, mocker):
    """Clean master-only and full-only results on the same catalog."""
    _patch_clean(mocker, True)
    sandbox.run_master()
    uploaded = sandbox.share_names()
    _wipe(sandbox)
    sandbox.run_full(_fresh_db())
    installed = sandbox.installed_files()
    _wipe(sandbox)
    return uploaded, installed


@pytest.mark.parametrize("clean", [True, False])
@pytest.mark.parametrize("leftovers", ["none", "full_style", "staging", "both"])
def test_dual_with_stale_download_cache(sandbox, mocker, caplog, clean, leftovers):
    uploaded, installed = _baseline(sandbox, mocker)
    assert len(uploaded) == EXPECTED and installed  # guards against a vacuous run
    # Plant only for setups that get processed: unmatched/bundle ids are never
    # touched, so their leftovers legitimately stay.
    ids = {d["id"] for d in _catalog() if any(d["id"] in n for n in uploaded)}
    assert len(ids) == EXPECTED

    _patch_clean(mocker, clean)
    if leftovers in ("full_style", "both"):
        assert _plant_full_style(sandbox, ids) == EXPECTED
    if leftovers in ("staging", "both"):
        _plant_staging(sandbox, ids)

    caplog.set_level(logging.INFO, logger="TrackTitanDownloader")
    manager = sandbox.run_dual(_fresh_db())

    assert _failures(caplog) == []
    assert any(f"Uploaded {EXPECTED} setup(s) to the share, 0 failed." in r.getMessage() for r in caplog.records)
    assert manager.installed_count == len(uploaded) == EXPECTED
    assert manager.install_failed_count == 0
    assert sandbox.share_names() == uploaded
    assert sandbox.installed_files() == installed
    if clean:
        assert _leftover_archives(sandbox) == []
        assert [p for p in sandbox.downloads.iterdir() if p.is_dir()] == []


@pytest.mark.parametrize("clean", [True, False])
def test_dual_when_expected_file_already_present_and_staging_leftover(sandbox, mocker, caplog, clean):
    """Expected-name archives (left by an earlier MASTER run with cleanup off)
    plus dual-<id>.zip leftovers: nothing fails."""
    _patch_clean(mocker, False)
    sandbox.run_master()
    uploaded = sandbox.share_names()
    assert len(uploaded) == EXPECTED
    assert _leftover_archives(sandbox)
    shutil.rmtree(sandbox.share)
    sandbox.share.mkdir()
    _plant_staging(sandbox)

    _patch_clean(mocker, clean)
    caplog.set_level(logging.INFO, logger="TrackTitanDownloader")
    manager = sandbox.run_dual(_fresh_db())

    assert _failures(caplog) == []
    assert manager.installed_count == EXPECTED and manager.install_failed_count == 0
    assert sandbox.share_names() == uploaded


@pytest.mark.parametrize("planter", [_plant_full_style, _plant_staging])
def test_master_with_stale_download_cache(sandbox, mocker, caplog, planter):
    _patch_clean(mocker, True)
    sandbox.run_master()
    expected = sandbox.share_names()
    assert len(expected) == EXPECTED
    _wipe(sandbox)

    planter(sandbox)
    caplog.set_level(logging.INFO, logger="TrackTitanDownloader")
    sandbox.run_master()

    assert _failures(caplog) == []
    assert sandbox.share_names() == expected
