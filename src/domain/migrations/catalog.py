import sqlite3

from domain.migrations.runner import Migration


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _migration_baseline(conn: sqlite3.Connection) -> None:
    """Schema as of v1.2.1, before this migrations framework existed: the full
    `installed_setups` table plus the four ad-hoc ALTER TABLE steps that used
    to live inline in SetupDb.create_tables(). Column existence is checked via
    PRAGMA table_info rather than try/except OperationalError: unlike the old
    approach, this migration is replayed unconditionally on every pre-existing
    DB the very first time this framework runs (before schema_version is
    known), so it must tell "already applied" apart from "needs applying"
    without relying on a caught exception."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS installed_setups (
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
            matched_track_id TEXT,
            sha256 TEXT,
            setup_type TEXT NOT NULL DEFAULT 'HYMO'
        )
    """)
    for column, ddl in (
        ("track_found", "ALTER TABLE installed_setups ADD COLUMN track_found INTEGER"),
        ("installation_base_path", "ALTER TABLE installed_setups ADD COLUMN installation_base_path TEXT"),
        ("installation_folder", "ALTER TABLE installed_setups ADD COLUMN installation_folder TEXT"),
        ("matched_track_id", "ALTER TABLE installed_setups ADD COLUMN matched_track_id TEXT"),
        ("sha256", "ALTER TABLE installed_setups ADD COLUMN sha256 TEXT"),
        ("setup_type", "ALTER TABLE installed_setups ADD COLUMN setup_type TEXT NOT NULL DEFAULT 'HYMO'"),
    ):
        if not _column_exists(conn, "installed_setups", column):
            conn.execute(ddl)


def _migration_normalize_car_track(conn: sqlite3.Connection) -> None:
    """One-time data fix: before this version, HYMO rows stored the raw
    TrackTitan car/track name while GO rows stored the already-sanitized
    Dropbox-folder name (see domain.setup.sanitize_identity) - car/track names
    containing '-', '/' or '\\' therefore never matched between the two,
    breaking both the Setup installati UI grouping and GO's HYMO-existence
    gate. Runs once; add_installed_setup/update_installed_setup sanitize every
    write from this version on, so this never needs to re-run."""
    from domain.setup import sanitize_identity

    rows = conn.execute("SELECT setup_id, car, track FROM installed_setups").fetchall()
    for setup_id, car, track in rows:
        new_car = sanitize_identity(car) if car else car
        new_track = sanitize_identity(track) if track else track
        if new_car != car or new_track != track:
            conn.execute(
                "UPDATE installed_setups SET car = ?, track = ? WHERE setup_id = ?",
                (new_car, new_track, setup_id),
            )


CATALOG: list[Migration] = [
    Migration("1.2.1", "Baseline schema (installed_setups with all columns through v1.2.1)", _migration_baseline),
    Migration("1.3.0", "Normalize car/track to the sanitized form shared with GO Setups", _migration_normalize_car_track),
]
