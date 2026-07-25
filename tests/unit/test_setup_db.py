import pytest
from domain.setup_db import InstalledSetup


def _setup(id="s1", track="Spa", car="Ferrari", last_updated=1000):
    from domain.setup import Setup
    return Setup({
        "id": id,
        "title": "T",
        "setupCombos": [{"car": {"name": car}, "track": {"name": track}}],
        "hotlapLink": None,
        "lastUpdatedAt": last_updated,
        "isBundle": False,
    })


def test_create_tables_idempotent(in_memory_db):
    in_memory_db.create_tables()  # seconda chiamata non deve sollevare


def test_not_installed_on_empty_db(in_memory_db):
    assert in_memory_db.is_setup_installed_last_version(_setup()) is False


def test_add_then_installed(in_memory_db, tmp_path):
    s = _setup(id="abc", last_updated=5000)
    in_memory_db.add_installed_setup(s, [], True, tmp_path / "Spa")
    assert in_memory_db.is_setup_installed_last_version(s) is True


def test_newer_version_not_installed(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="abc", last_updated=1000), [], True, tmp_path / "Spa")
    assert in_memory_db.is_setup_installed_last_version(_setup(id="abc", last_updated=9999)) is False


def test_add_performs_upsert(in_memory_db, tmp_path):
    dir_ = tmp_path / "Spa"
    in_memory_db.add_installed_setup(_setup(id="abc", last_updated=100), [], True, dir_)
    in_memory_db.add_installed_setup(_setup(id="abc", last_updated=200), [], True, dir_)
    cur = in_memory_db.conn.execute("SELECT COUNT(*) FROM installed_setups WHERE setup_id='abc'")
    assert cur.fetchone()[0] == 1


def test_fetch_setup_files_returns_names(in_memory_db, tmp_path):
    files = [tmp_path / "a.svm", tmp_path / "b.svm"]
    in_memory_db.add_installed_setup(_setup(id="xyz"), files, True, tmp_path / "T")
    assert set(in_memory_db.fetch_setup_files("xyz")) == {"a.svm", "b.svm"}


def test_fetch_setup_files_missing_id(in_memory_db):
    assert in_memory_db.fetch_setup_files("ghost") == []


def test_is_track_found_true(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="t1"), [], True, tmp_path / "T")
    assert in_memory_db.is_track_found("t1") is True


def test_is_track_found_false(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="t2"), [], False, tmp_path / "T")
    assert in_memory_db.is_track_found("t2") is False


def test_is_track_found_missing_id(in_memory_db):
    assert in_memory_db.is_track_found("ghost") is False


def test_fetch_tracks_not_found(in_memory_db, tmp_path):
    dir_ = tmp_path / "T"
    in_memory_db.add_installed_setup(_setup(id="found"), [], True, dir_)
    in_memory_db.add_installed_setup(_setup(id="notfound"), [], False, dir_)
    ids = [r.setup_id for r in in_memory_db.fetch_tracks_not_found()]
    assert "notfound" in ids
    assert "found" not in ids


def test_update_installed_setup(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="upd"), [], False, tmp_path / "Old")
    row = in_memory_db.fetch_tracks_not_found()[0]
    row.track_found = True
    row.installation_folder = "New"
    in_memory_db.update_installed_setup(row)
    assert in_memory_db.is_track_found("upd") is True


def test_is_installed_last_version_by_id_ts(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="zz", last_updated=500), [], True, tmp_path / "T")
    assert in_memory_db.is_installed_last_version("zz", 500) is True
    assert in_memory_db.is_installed_last_version("zz", 400) is True
    assert in_memory_db.is_installed_last_version("zz", 600) is False
    assert in_memory_db.is_installed_last_version("absent", 1) is False


def test_fetch_all_installed_setups_includes_all_rows(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="found", track="Spa"), [], True, tmp_path / "T")
    in_memory_db.add_installed_setup(_setup(id="notfound", track="Imola"), [], False, tmp_path / "T")

    ids = [r.setup_id for r in in_memory_db.fetch_all_installed_setups()]

    assert "found" in ids
    assert "notfound" in ids


def test_fetch_all_installed_setups_orders_by_track_then_car(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="z", track="Zolder", car="Ferrari"), [], True, tmp_path / "T")
    in_memory_db.add_installed_setup(_setup(id="a2", track="Imola", car="Porsche"), [], True, tmp_path / "T")
    in_memory_db.add_installed_setup(_setup(id="a1", track="Imola", car="Ferrari"), [], True, tmp_path / "T")

    rows = in_memory_db.fetch_all_installed_setups()

    assert [(r.track, r.car) for r in rows] == [
        ("Imola", "Ferrari"),
        ("Imola", "Porsche"),
        ("Zolder", "Ferrari"),
    ]


def test_fetch_all_installed_setups_empty_db(in_memory_db):
    assert in_memory_db.fetch_all_installed_setups() == []


def test_installed_setup_from_row():
    row = (
        "id1", "Spa", "Ferrari", 1000, 2000, "http://lap",
        '{"x":1}', '["a.svm"]', 1, "/base", "folder", "Spa",
        "abc123", "GO"
    )
    s = InstalledSetup.from_row(row)
    assert s.setup_id == "id1"
    assert s.api_data == {"x": 1}
    assert s.file_names == ["a.svm"]
    assert s.track_found is True
    assert s.matched_track_id == "Spa"
    assert s.sha256 == "abc123"
    assert s.setup_type == "GO"


def test_add_installed_setup_stores_matched_track_id(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="m1", track="Bahrain - WEC"), [], True, tmp_path / "Bahrain", "Bahrain")
    row = in_memory_db.fetch_all_installed_setups()[0]
    assert row.matched_track_id == "Bahrain"


def test_add_installed_setup_defaults_matched_track_id_to_none(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="m2", track="Mystery"), [], False, tmp_path / "Mystery-HYMO")
    row = in_memory_db.fetch_all_installed_setups()[0]
    assert row.matched_track_id is None


def test_update_installed_setup_persists_matched_track_id(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="m3", track="Mystery"), [], False, tmp_path / "Mystery-HYMO")
    row = in_memory_db.fetch_all_installed_setups()[0]
    row.matched_track_id = "Imola"
    row.track_found = True
    in_memory_db.update_installed_setup(row)
    updated = in_memory_db.fetch_all_installed_setups()[0]
    assert updated.matched_track_id == "Imola"


def test_fetch_installed_setup_returns_the_matching_row(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="s1", track="Spa"), [], True, tmp_path / "Spa")
    setup = in_memory_db.fetch_installed_setup("s1")
    assert setup is not None
    assert setup.setup_id == "s1"
    assert setup.track == "Spa"


def test_fetch_installed_setup_missing_id_returns_none(in_memory_db):
    assert in_memory_db.fetch_installed_setup("ghost") is None


def test_delete_installed_setup_removes_the_row(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="s1"), [], True, tmp_path / "Spa")
    in_memory_db.delete_installed_setup("s1")
    assert in_memory_db.fetch_installed_setup("s1") is None


def test_delete_installed_setup_missing_id_is_a_noop(in_memory_db):
    in_memory_db.delete_installed_setup("ghost")  # must not raise


# --- sha256 / setup_type ------------------------------------------------------


def test_add_installed_setup_defaults_setup_type_to_hymo_and_sha256_to_none(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(_setup(id="d1"), [], True, tmp_path / "Spa")
    row = in_memory_db.fetch_installed_setup("d1")
    assert row.setup_type == "HYMO"
    assert row.sha256 is None


def test_add_installed_setup_stores_sha256_and_setup_type(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(
        _setup(id="g1"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="deadbeef",
    )
    row = in_memory_db.fetch_installed_setup("g1")
    assert row.setup_type == "GO"
    assert row.sha256 == "deadbeef"


def test_add_installed_setup_upsert_updates_sha256(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(
        _setup(id="g2"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="hash-v1",
    )
    in_memory_db.add_installed_setup(
        _setup(id="g2"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="hash-v2",
    )
    row = in_memory_db.fetch_installed_setup("g2")
    assert row.sha256 == "hash-v2"


def test_update_installed_setup_persists_sha256_and_setup_type(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(
        _setup(id="u1"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="hash-v1",
    )
    row = in_memory_db.fetch_installed_setup("u1")
    row.sha256 = "hash-v2"
    in_memory_db.update_installed_setup(row)
    updated = in_memory_db.fetch_installed_setup("u1")
    assert updated.sha256 == "hash-v2"
    assert updated.setup_type == "GO"


def test_migration_backfills_setup_type_and_leaves_sha256_null(mocker, tmp_path):
    """A pre-existing DB, created before this feature, has only the original 12
    columns - the ADD COLUMN migration must backfill setup_type via its column
    default, and leave sha256 NULL for that old row."""
    import sqlite3
    legacy_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(legacy_path)
    conn.execute("""
        CREATE TABLE installed_setups (
            setup_id TEXT PRIMARY KEY,
            track TEXT,
            car TEXT,
            install_date INTEGER,
            setup_last_update INTEGER,
            hotlap_link TEXT,
            api_data TEXT,
            file_names TEXT,
            track_found INTEGER,
            installation_base_path TEXT,
            installation_folder TEXT,
            matched_track_id TEXT
        )
    """)
    conn.execute(
        "INSERT INTO installed_setups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("old1", "Spa", "Ferrari", 1000, 2000, None, "{}", "[]", 1, "/base", "Spa", None),
    )
    conn.commit()
    conn.close()

    mocker.patch("domain.setup_db.DB_PATH", legacy_path)
    from domain.setup_db import SetupDb
    db = SetupDb()

    row = db.fetch_installed_setup("old1")
    assert row.setup_type == "HYMO"
    assert row.sha256 is None


# --- fetch_installed_go_setup -------------------------------------------------


def test_fetch_installed_go_setup_returns_the_matching_row(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(
        _setup(id="go1", car="Ferrari", track="Spa"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="hash1",
    )
    row = in_memory_db.fetch_installed_go_setup("Ferrari", "Spa")
    assert row is not None
    assert row.setup_id == "go1"
    assert row.sha256 == "hash1"


def test_fetch_installed_go_setup_returns_none_when_absent(in_memory_db):
    assert in_memory_db.fetch_installed_go_setup("Ferrari", "Spa") is None


def test_fetch_installed_go_setup_reflects_updated_row_after_a_second_upsert(in_memory_db, tmp_path):
    in_memory_db.add_installed_setup(
        _setup(id="go1", car="Ferrari", track="Spa"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="hash-v1",
    )
    # A version bump reuses the same setup_id (as SlaveManager._process_go
    # would, after looking it up by car+track) so it stays one row.
    in_memory_db.add_installed_setup(
        _setup(id="go1", car="Ferrari", track="Spa"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="hash-v2",
    )
    row = in_memory_db.fetch_installed_go_setup("Ferrari", "Spa")
    assert row.sha256 == "hash-v2"
    cur = in_memory_db.conn.execute(
        "SELECT COUNT(*) FROM installed_setups WHERE car='Ferrari' AND track='Spa' AND setup_type='GO'"
    )
    assert cur.fetchone()[0] == 1


def test_fetch_installed_go_setup_ignores_a_hymo_row_with_the_same_car_and_track(in_memory_db, tmp_path):
    """A TrackTitan setup and a GO archive can legitimately share a car+track
    pair - the lookup must not accidentally reuse the HYMO row's real
    TrackTitan id as a GO setup_id."""
    in_memory_db.add_installed_setup(
        _setup(id="real-tracktitan-uuid", car="Ferrari", track="Spa"), [], True, tmp_path / "Spa",
        setup_type="HYMO", sha256="hymo-hash",
    )
    assert in_memory_db.fetch_installed_go_setup("Ferrari", "Spa") is None

    in_memory_db.add_installed_setup(
        _setup(id="go-uuid", car="Ferrari", track="Spa"), [], True, tmp_path / "Spa",
        setup_type="GO", sha256="go-hash",
    )
    row = in_memory_db.fetch_installed_go_setup("Ferrari", "Spa")
    assert row is not None
    assert row.setup_id == "go-uuid"
