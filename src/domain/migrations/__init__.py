"""DB schema migrations, kept separate from SetupDb's own CRUD code.

Add a new migration by appending a `Migration(version, description, apply)` to
`CATALOG` in catalog.py - never edit or remove an already-shipped one, since
existing installs may still need to replay it. The schema gate converges to
SCHEMA_TARGET_VERSION, the highest version found in CATALOG - deliberately
independent of core.version.APP_VERSION (a display-only release marker), so
adding a migration during development never requires bumping that file too.
"""
import sqlite3

from domain.migrations.catalog import CATALOG
from domain.migrations.runner import Migration, parse_version
from domain.migrations.runner import run_migrations as _run_migrations

__all__ = ["run_migrations", "Migration", "parse_version", "CATALOG", "SCHEMA_TARGET_VERSION"]

SCHEMA_TARGET_VERSION: str = max((m.version for m in CATALOG), key=parse_version) if CATALOG else "0.0.0"


def run_migrations(conn: sqlite3.Connection) -> None:
    _run_migrations(conn, migrations=CATALOG, target_version=SCHEMA_TARGET_VERSION)
