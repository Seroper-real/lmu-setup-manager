import sqlite3

from domain.migrations.runner import Migration


def _migration_baseline(conn: sqlite3.Connection) -> None:
    """Full installed_setups schema, created in one shot. No backward
    compatibility before this version: a pre-existing DB with an older
    column set is not migrated forward and must be deleted/recreated to
    pick up this schema."""
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


CATALOG: list[Migration] = [
    Migration("2.0.0", "Baseline schema (installed_setups)", _migration_baseline),
]
