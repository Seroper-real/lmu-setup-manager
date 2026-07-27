import json
import logging
import re
from pathlib import Path
from typing import Callable, Optional, TypeVar

import requests

log = logging.getLogger("TrackTitanDownloader")

T = TypeVar("T")


def load_local_json(path: Path) -> Optional[dict]:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_remote_json(url: str, timeout: float, label: str) -> Optional[dict]:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log.error(f"Cannot download {label} file from Github. Error: {e}")
        return None


def load_catalog_with_fallback(
    local_path: Path,
    remote_enabled: bool,
    remote_url: str,
    remote_timeout: float,
    label: str,
    process_fn: Callable[[dict], T],
) -> T:
    """Load a mapping file with the same no-versioning precedence used for
    tracks: the remote mirror wins whenever it's reachable, the bundled local
    file is only an offline/disabled-remote fallback.

    `process_fn(dict) -> T` turns the raw JSON into whatever the caller needs
    (e.g. compiled regex patterns) and must raise on any schema problem (a
    missing/malformed field). If the remote file is reachable and is valid
    JSON but `process_fn` raises against it (incompatible schema, not just a
    network/decode failure), this falls back to the local file instead of
    crashing the app - the local file's own `process_fn` failure, if any, is
    NOT caught, since there is nothing left to fall back to.
    """
    if remote_enabled:
        remote_json = load_remote_json(remote_url, remote_timeout, label)
        if remote_json is not None:
            try:
                return process_fn(remote_json)
            except Exception as e:
                log.error(f"Remote {label} file is malformed, falling back to local. Error: {e}")

    local_json = load_local_json(local_path)
    if local_json is None:
        raise RuntimeError(f"No {label} file found. Both local and remote files are missing, inaccessible, or malformed.")
    return process_fn(local_json)


def compile_patterns(entries: list[dict], *, pattern_key: str, name_key: str) -> list[tuple[re.Pattern[str], str]]:
    """Turn a list of {name_key: str, pattern_key: [regex, ...]} dicts into a
    flat list of (compiled_pattern, name) pairs, order preserved from
    `entries`. Raises KeyError if an entry is missing `name_key` - that's a
    genuine schema problem callers (via load_catalog_with_fallback) should
    fall back on, not silently skip."""
    patterns: list[tuple[re.Pattern[str], str]] = []
    for entry in entries:
        name = entry[name_key]
        for raw_pattern in entry.get(pattern_key, []):
            try:
                patterns.append((re.compile(raw_pattern, re.IGNORECASE), name))
            except re.error as e:
                log.warning(f"Invalid regex pattern '{raw_pattern}' for '{name}': {e}. Skipping.")
    return patterns


def extract_value_map(entries: list[dict], *, name_key: str, value_key: str) -> dict[str, str]:
    """Turn a list of {name_key: str, value_key: str, ...} dicts into a flat
    name_key -> value_key dict, order preserved from `entries`. Unlike
    compile_patterns' name_key, `value_key` is optional per entry - an entry
    missing it is silently skipped rather than raising, since it's an
    auxiliary field (e.g. a car's class) that not every caller needs present
    on every entry."""
    values: dict[str, str] = {}
    for entry in entries:
        value = entry.get(value_key)
        if value is not None:
            values[entry[name_key]] = value
    return values
