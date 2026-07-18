"""A track that was unknown at install time, then added to tracks.json.

The next run must relocate the already-installed .svm files out of the -HYMO
fallback folder and into the real one, updating the DB record.
"""
import pytest

from sandbox_harness import make_setup

SETUP_ID = "cccccccc-dddd-4eee-8fff-000000000001"
TS = 1700000000


@pytest.fixture
def installed_unmapped(sandbox, in_memory_db):
    """Install one setup while tracks.json knows nothing about its track."""
    sandbox.set_tracks([])
    sandbox.write_catalog([make_setup(SETUP_ID, "Imola - WEC", ts=TS)])
    sandbox.add_archive(SETUP_ID, {"imola.svm": "data"})

    sandbox.run_full(in_memory_db)

    assert sandbox.installed_files() == {"Imola - WEC-HYMO/imola.svm"}
    assert in_memory_db.is_track_found(SETUP_ID) is False
    return sandbox, in_memory_db


def test_adding_the_mapping_relocates_the_setup(installed_unmapped):
    sandbox, db = installed_unmapped

    sandbox.set_tracks([("imola", "Imola")])
    sandbox.run_full(db)

    assert sandbox.installed_files() == {"Imola/imola.svm"}
    assert db.is_track_found(SETUP_ID) is True


def test_relocation_removes_the_emptied_hymo_folder(installed_unmapped):
    sandbox, db = installed_unmapped

    sandbox.set_tracks([("imola", "Imola")])
    sandbox.run_full(db)

    assert not (sandbox.lmu / "Imola - WEC-HYMO").exists()


def test_relocation_updates_the_installation_path_in_the_db(installed_unmapped):
    sandbox, db = installed_unmapped

    sandbox.set_tracks([("imola", "Imola")])
    sandbox.run_full(db)

    # A later run must not try to relocate it again.
    assert db.fetch_tracks_not_found() == []


def test_setup_stays_put_while_the_track_remains_unmapped(installed_unmapped):
    sandbox, db = installed_unmapped

    sandbox.run_full(db)

    assert sandbox.installed_files() == {"Imola - WEC-HYMO/imola.svm"}
    assert db.is_track_found(SETUP_ID) is False


def test_first_matching_pattern_wins(sandbox, in_memory_db):
    sandbox.set_tracks([("imola", "Imola"), ("wec", "SomewhereElse")])
    sandbox.write_catalog([make_setup(SETUP_ID, "Imola - WEC", ts=TS)])
    sandbox.add_archive(SETUP_ID, {"imola.svm": "data"})

    sandbox.run_full(in_memory_db)

    assert sandbox.installed_files() == {"Imola/imola.svm"}
