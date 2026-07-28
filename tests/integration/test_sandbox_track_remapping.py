"""Track-pattern matching behavior around installs, exercised through the sandbox."""
from sandbox_harness import make_setup

SETUP_ID = "cccccccc-dddd-4eee-8fff-000000000001"
TS = 1700000000


def test_first_matching_pattern_wins(sandbox, in_memory_db):
    sandbox.set_tracks([("imola", "Imola"), ("wec", "SomewhereElse")])
    sandbox.write_catalog([make_setup(SETUP_ID, "Imola - WEC", ts=TS)])
    sandbox.add_archive(SETUP_ID, {"imola.svm": "data"})

    sandbox.run_full(in_memory_db)

    assert sandbox.installed_files() == {"Imola/imola.svm"}


def test_a_fresh_unmapped_track_is_skipped_not_installed_under_a_fallback_folder(sandbox, in_memory_db):
    """An unmatched track is ignored outright - never installed under a
    "-HYMO" placeholder folder."""
    sandbox.set_tracks([])
    sandbox.write_catalog([make_setup(SETUP_ID, "Imola - WEC", ts=TS)])
    sandbox.add_archive(SETUP_ID, {"imola.svm": "data"})

    sandbox.run_full(in_memory_db)

    assert sandbox.installed_files() == set()
    assert in_memory_db.fetch_installed_setup(SETUP_ID) is None
