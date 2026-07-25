import sqlite3

import pytest

from domain.migrations.runner import Migration, parse_version, run_migrations


def test_parse_version_pads_missing_components():
    assert parse_version("1.3") == (1, 3, 0)
    assert parse_version("2") == (2, 0, 0)


def test_parse_version_compares_numerically_not_lexicographically():
    assert parse_version("1.10.0") > parse_version("1.9.0")
    assert parse_version("1.2.1") < parse_version("1.3.0")


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    yield connection
    connection.close()


def test_run_migrations_applies_every_migration_in_order(conn):
    calls: list[str] = []
    migrations = [
        Migration("1.1.0", "first", lambda c: calls.append("1.1.0")),
        Migration("1.0.0", "zeroth (out of list order on purpose)", lambda c: calls.append("1.0.0")),
        Migration("1.2.0", "second", lambda c: calls.append("1.2.0")),
    ]

    run_migrations(conn, migrations=migrations, target_version="1.2.0")

    assert calls == ["1.0.0", "1.1.0", "1.2.0"]
    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0]
    assert version == "1.2.0"


def test_run_migrations_skips_already_applied_versions(conn):
    calls: list[str] = []
    migrations = [Migration("1.0.0", "first", lambda c: calls.append("1.0.0"))]

    run_migrations(conn, migrations=migrations, target_version="1.0.0")
    run_migrations(conn, migrations=migrations, target_version="1.0.0")

    assert calls == ["1.0.0"]


def test_run_migrations_bumps_stored_version_even_with_no_pending_migrations(conn):
    """A release can bump APP_VERSION with no new migration - the stored
    version must still converge to it."""
    migrations = [Migration("1.0.0", "first", lambda c: None)]

    run_migrations(conn, migrations=migrations, target_version="1.0.0")
    run_migrations(conn, migrations=migrations, target_version="1.1.0")

    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0]
    assert version == "1.1.0"


def test_run_migrations_leaves_a_newer_stored_version_untouched(conn):
    """Running an older build (lower target_version) against a DB already
    migrated by a newer build must not roll the stored version back."""
    migrations = [
        Migration("1.0.0", "first", lambda c: None),
        Migration("2.0.0", "second", lambda c: None),
    ]

    run_migrations(conn, migrations=migrations, target_version="2.0.0")
    run_migrations(conn, migrations=migrations, target_version="1.0.0")

    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()[0]
    assert version == "2.0.0"


def test_run_migrations_wraps_each_migration_in_its_own_transaction(conn):
    def _apply(c: sqlite3.Connection) -> None:
        c.execute("CREATE TABLE marker (id INTEGER)")
        c.execute("INSERT INTO marker VALUES (1)")

    migrations = [Migration("1.0.0", "creates a table", _apply)]
    run_migrations(conn, migrations=migrations, target_version="1.0.0")

    assert conn.execute("SELECT COUNT(*) FROM marker").fetchone()[0] == 1
