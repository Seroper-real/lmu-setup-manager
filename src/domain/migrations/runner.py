import logging
import sqlite3
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger("TrackTitanDownloader")


@dataclass
class Migration:
    """One versioned, idempotent step against the app DB. `apply` receives the
    raw connection and must not commit/rollback itself - run_migrations wraps
    each one in its own transaction."""
    version: str
    description: str
    apply: Callable[[sqlite3.Connection], None]


def parse_version(value: str) -> tuple[int, int, int]:
    """"1.10.0" -> (1, 10, 0). Never compare version strings lexicographically -
    "1.10.0" < "1.9.0" as strings, which is wrong."""
    parts = [int(p) for p in value.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version TEXT NOT NULL
            )
        """)


def _read_version(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    return row[0] if row else "0.0.0"


def _write_version(conn: sqlite3.Connection, version: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO schema_version (id, version) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET version = excluded.version",
            (version,),
        )


def run_migrations(conn: sqlite3.Connection, migrations: list[Migration], target_version: str) -> None:
    """Bring `conn`'s schema up to `target_version` by applying every migration
    in `migrations` whose version is newer than what's stored in
    `schema_version` (order in `migrations` is not assumed - each is compared
    against the stored version independently). Each migration runs in its own
    transaction. The stored version is bumped to `target_version` whenever it
    was behind, even if no migration actually ran (a release can bump the app
    version with no schema change) - this also covers a downgrade (running an
    older build against a newer DB) by leaving the stored version untouched."""
    _ensure_version_table(conn)
    stored = _read_version(conn)
    stored_tuple = parse_version(stored)

    for migration in sorted(migrations, key=lambda m: parse_version(m.version)):
        if parse_version(migration.version) > stored_tuple:
            log.info(f"Applying DB migration {migration.version}: {migration.description}")
            with conn:
                migration.apply(conn)

    if parse_version(stored) < parse_version(target_version):
        _write_version(conn, target_version)
