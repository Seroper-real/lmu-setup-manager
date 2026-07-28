import json
import os
import re
import sqlite3
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from core.utils import get_data_dir, get_path

# Redirected under any MOCK_* sandbox switch, same as core.config.DB_PATH.
# Duplicated here (rather than imported from core.config) because core.config
# itself imports this module - importing back would be circular. An earlier
# version of this file deliberately kept settings.db un-redirected so a
# --mock-lmu-only run could still use real credentials without re-entering
# them; that let a sandbox run's "restore factory settings" action wipe the
# real per-user settings.db (mode, language, TrackTitan/Dropbox credentials,
# custom track mappings). Never again: any mock flag now means settings.db
# lives under the sandbox root too, just like the setups DB does.
def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


_SANDBOX_MODE: bool = _env_flag("MOCK_TRACKTITAN") or _env_flag("MOCK_LMU") or _env_flag("MOCK_DROPBOX")
_SANDBOX_PATH: Path = get_path(os.getenv("MOCK_BASE_PATH") or "sandbox")

SETTINGS_DB_PATH: Path = (
    (_SANDBOX_PATH / "data" / "settings.db") if _SANDBOX_MODE else (get_data_dir() / "settings.db")
)

# Mirrors config/config.json's old shape. mode/ui deliberately differ from the
# values that were checked into that file ("slave"/dismissed=True) - those were
# the developer's local working state, not intentional shipped defaults. "full"
# and dismissed=False are the real first-run behavior.
DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "full",
    "logging": {"level": "DEBUG"},
    "network": {
        "base_url": "https://services.tracktitan.io/api",
        "consumer_id": "trackTitan",
        "page_size": 64,
        "min_delay": 0.5,
        "max_delay": 1.5,
        "timeout": 30,
    },
    "paths": {
        "download": {"base_path": "downloads", "clean_download_after_copy": True},
        "setups": {
            "overwrite": False,
            "delete_previous_version": True,
            "lmu_base_path": r"C:\Program Files (x86)\Steam\steamapps\common\Le Mans Ultimate\UserData\player\Settings",
            "file_extensions": [".svm"],
        },
    },
    "remote_mappings": {
        "enabled": True,
        "url": "https://raw.githubusercontent.com/Seroper-real/lmu-setup-manager/refs/heads/main/config/mapping.json",
        "timeout": 5,
    },
    "dropbox": {"folder": "/lmu-setups", "timeout": 30, "upload_workers": 4},
    "ui": {"language": "it", "hymo_warning_dismissed": False},
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _upsert_manual_mapping_row(conn: sqlite3.Connection, mapping_type: str, name: str, pattern: str) -> None:
    """Append `pattern` (one or more "|"-joined matcher alternatives) to the
    (type, name) row, deduping exact literal alternatives already present;
    insert a new row if none exists yet. Operates on an already-open
    connection/transaction - the caller owns commit/rollback, so this can run
    both from the public upsert_manual_mapping() below and from the one-time
    tracks-table migration in the same transaction as the rest of table setup."""
    row = conn.execute(
        "SELECT id, matcher FROM manual_mapping WHERE type = ? AND name = ?", (mapping_type, name)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO manual_mapping (id, type, name, matcher) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), mapping_type, name, pattern),
        )
        return
    mapping_id, existing_matcher = row
    existing_parts = set(existing_matcher.split("|"))
    new_parts = [p for p in pattern.split("|") if p not in existing_parts]
    if not new_parts:
        return
    conn.execute(
        "UPDATE manual_mapping SET matcher = ? WHERE id = ?",
        (existing_matcher + "|" + "|".join(new_parts), mapping_id),
    )


def _ensure_tables(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            )
        """)
        # User-added customizations only (the "Correggi" UI action, plus the
        # end-of-run "unmatched setups" correction dialog) - layered on top of
        # config/mapping.json's file-derived mapping, never seeded with it.
        # One row per (type, name): `matcher` holds every raw TrackTitan/Dropbox
        # alternative the user has taught this official name so far, joined with
        # "|" (see upsert_manual_mapping) - equivalent to a list of patterns
        # since re.search treats "|" as alternation.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS manual_mapping (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                matcher TEXT NOT NULL,
                UNIQUE(type, name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS env_secrets (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO config (id, data) VALUES (1, ?)",
            (json.dumps(DEFAULT_CONFIG),),
        )
        _migrate_legacy_tracks_table(conn)


def _migrate_legacy_tracks_table(conn: sqlite3.Connection) -> None:
    """One-time fold of the pre-manual_mapping "tracks" table (the old
    per-track-only Correggi storage) into manual_mapping(type="track"), then
    drop it. Guarded by a sqlite_master check so this is a no-op on every call
    after the first - `tracks` is gone by then."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tracks'"
    ).fetchone()
    if not exists:
        return
    rows = conn.execute("SELECT lmu_folder_name, tt_patterns FROM tracks").fetchall()
    for lmu_folder_name, patterns_json in rows:
        patterns = json.loads(patterns_json)
        if patterns:
            _upsert_manual_mapping_row(conn, "track", lmu_folder_name, "|".join(patterns))
    conn.execute("DROP TABLE tracks")


def _connect() -> sqlite3.Connection:
    SETTINGS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SETTINGS_DB_PATH)
    _ensure_tables(conn)
    return conn


def get_config() -> dict[str, Any]:
    # Deep-merged with DEFAULT_CONFIG rather than a raw pass-through: a config
    # row already saved by an older app version won't have keys introduced
    # since (e.g. "remote_mappings", replacing the old "remote_tracks"), and a
    # bare bracket access on a missing key downstream (core.config) would
    # raise KeyError on first launch after an upgrade for every existing user.
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM config WHERE id = 1").fetchone()
        return _deep_merge(DEFAULT_CONFIG, json.loads(row[0])) if row else deepcopy(DEFAULT_CONFIG)
    finally:
        conn.close()


def reset_to_factory_defaults() -> None:
    """Wipe config, custom track/car mappings, and secrets, then reseed config
    with DEFAULT_CONFIG - the Settings "Restore factory settings" danger-zone
    action."""
    conn = _connect()
    try:
        with conn:
            conn.execute("DELETE FROM config")
            conn.execute("DELETE FROM manual_mapping")
            conn.execute("DELETE FROM env_secrets")
            conn.execute("INSERT INTO config (id, data) VALUES (1, ?)", (json.dumps(DEFAULT_CONFIG),))
    finally:
        conn.close()


def save_config(patch: dict[str, Any]) -> None:
    conn = _connect()
    try:
        row = conn.execute("SELECT data FROM config WHERE id = 1").fetchone()
        current = json.loads(row[0]) if row else deepcopy(DEFAULT_CONFIG)
        merged = _deep_merge(current, patch)
        with conn:
            conn.execute(
                "INSERT INTO config (id, data) VALUES (1, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                (json.dumps(merged),),
            )
    finally:
        conn.close()


def get_secret(key: str) -> Optional[str]:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM env_secrets WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def save_secrets(values: dict[str, str]) -> None:
    conn = _connect()
    try:
        with conn:
            for key, value in values.items():
                conn.execute(
                    "INSERT INTO env_secrets (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
    finally:
        conn.close()


def get_manual_mappings(mapping_type: str) -> list[dict[str, Any]]:
    """User-added "Correggi"/unmatched-setup corrections for one type
    ("track" or "car"), in the order they were added. `matcher` is a single
    "|"-joined regex - pass it as a one-element list to compile_patterns()."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT name, matcher FROM manual_mapping WHERE type = ? ORDER BY rowid", (mapping_type,)
        ).fetchall()
        return [{"name": name, "matcher": matcher} for name, matcher in rows]
    finally:
        conn.close()


def upsert_manual_mapping(mapping_type: str, name: str, raw_value: str) -> None:
    """Teach `name` (an official mapping.json value) to also match
    `raw_value` (raw TrackTitan/Dropbox text). Appends to the existing
    (type, name) row's matcher if one exists, otherwise creates a new row -
    never a second row for the same (type, name) pair."""
    conn = _connect()
    try:
        with conn:
            _upsert_manual_mapping_row(conn, mapping_type, name, re.escape(raw_value))
    finally:
        conn.close()
