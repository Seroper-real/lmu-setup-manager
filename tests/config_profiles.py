"""Versioned test configuration, layered like Spring's application-{profile}.yml.

`tests/resources/config.test.json` is the base. Each profile is a delta file
`config.test-{profile}.json` holding only the keys it overrides; profiles are
deep-merged onto the base, in the order given, so they compose:

    build_config("master")

The sandbox is no longer expressible in this config: it lives entirely in the
MOCK_* environment variables now, which tests set through the `load_config` fixture.
"""
import json
import sqlite3
from pathlib import Path
from typing import Any

from core.settings_db import _deep_merge

RESOURCES: Path = Path(__file__).resolve().parent / "resources"
BASE_PROFILE: str = "config.test.json"


def _read(name: str) -> dict[str, Any]:
    path = RESOURCES / name
    if not path.exists():
        available = sorted(p.stem.split("-", 1)[1] for p in RESOURCES.glob("config.test-*.json"))
        raise FileNotFoundError(f"No test config profile {path.name!r}. Available: {available}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_config(*profiles: str) -> dict[str, Any]:
    config = _read(BASE_PROFILE)
    for profile in profiles:
        config = _deep_merge(config, _read(f"config.test-{profile}.json"))
    return config


def seed_test_settings_db(data_dir: Path, *profiles: str) -> Path:
    """Materialize the merged profile config into {data_dir}/settings.db's config
    row, so core.config's own default-seed-if-empty path is a no-op in tests."""
    import core.settings_db as settings_db

    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "settings.db"
    conn = sqlite3.connect(db_path)
    try:
        settings_db._ensure_tables(conn)
        with conn:
            conn.execute(
                "INSERT INTO config (id, data) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                (json.dumps(build_config(*profiles)),),
            )
    finally:
        conn.close()
    return db_path
