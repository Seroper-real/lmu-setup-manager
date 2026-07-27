import json
import os
import sqlite3
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


def _ensure_tables(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data TEXT NOT NULL
            )
        """)
        # User-added customizations only (the "Correggi" UI action) - layered on
        # top of config/mapping.json's file-derived mapping, never seeded with it.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lmu_folder_name TEXT NOT NULL,
                tt_patterns TEXT NOT NULL
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
    """Wipe config, custom track mappings, and secrets, then reseed config with
    DEFAULT_CONFIG - the Settings "Restore factory settings" danger-zone action."""
    conn = _connect()
    try:
        with conn:
            conn.execute("DELETE FROM config")
            conn.execute("DELETE FROM tracks")
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


def get_custom_tracks() -> list[dict[str, Any]]:
    """User-added "Correggi" mappings only, in the order they were added."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT lmu_folder_name, tt_patterns FROM tracks ORDER BY id").fetchall()
        return [{"lmu_folder_name": name, "tt_patterns": json.loads(patterns)} for name, patterns in rows]
    finally:
        conn.close()


def upsert_track_pattern(lmu_folder_name: str, pattern: str) -> None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, tt_patterns FROM tracks WHERE lmu_folder_name = ?", (lmu_folder_name,)
        ).fetchone()
        with conn:
            if row is not None:
                track_id, patterns_json = row
                patterns = json.loads(patterns_json)
                patterns.append(pattern)
                conn.execute("UPDATE tracks SET tt_patterns = ? WHERE id = ?", (json.dumps(patterns), track_id))
            else:
                conn.execute(
                    "INSERT INTO tracks (lmu_folder_name, tt_patterns) VALUES (?, ?)",
                    (lmu_folder_name, json.dumps([pattern])),
                )
    finally:
        conn.close()


def get_custom_folder_names() -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT DISTINCT lmu_folder_name FROM tracks ORDER BY lmu_folder_name").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()
