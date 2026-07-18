import os
import shutil
from pathlib import Path
from typing import Any, Optional
from core.utils import get_path, get_data_dir
from core import settings_db

# Environment values counted as boolean-true for the MOCK_* sandbox switches.
_TRUTHY: set[str] = {"1", "true", "yes", "on"}

# Minimum length for a credential value to be considered present. TrackTitan's
# JWTs/user id are long, but Dropbox's App Console issues app keys/secrets as
# fixed 15-character strings - a single global threshold rejected those as
# "invalid" even when correctly configured, which is what broke Slave mode.
_MIN_CREDENTIAL_LENGTHS: dict[str, int] = {
    "ACCESS_TOKEN_LIST": 20,
    "ACCESS_TOKEN_DOWNLOAD": 20,
    "USER_ID": 20,
    "DROPBOX_APP_KEY": 15,
    "DROPBOX_APP_SECRET": 15,
    "DROPBOX_REFRESH_TOKEN": 20,
}


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUTHY


# Load config from settings_db (creates + seeds settings.db on first call).
_config = settings_db.get_config()

# ===== MODE =====
# full   : TrackTitan -> install locally (DB-backed). Original behavior.
# master : TrackTitan -> repackage -> upload to Dropbox (no DB).
# slave  : Dropbox -> install locally (DB-backed, FULL-compatible).
# The MODE env var (set directly or via main.py's --mode flag) wins over the
# stored config, so a local run can switch mode without touching settings.db.
VALID_MODES: set[str] = {"full", "master", "slave"}
MODE: str = str(os.getenv("MODE") or _config.get("mode", "full")).strip().lower()
if MODE not in VALID_MODES:
    raise RuntimeError(
        f"Invalid 'mode' {MODE!r}. Must be one of {sorted(VALID_MODES)}"
    )

# ===== SANDBOX =====
# Three independent mocks, orthogonal to MODE, that stand in for the external
# systems: the TrackTitan API, the LMU game folder, the Dropbox share. Read
# only from the environment (set directly or via main.py's --mock-* / --sandbox
# flags) so they are never persisted to settings.db. Any combination is valid,
# e.g. mock TrackTitan + real Dropbox exercises the real upload path without a
# TrackTitan subscription.
MOCK_TRACKTITAN: bool = _env_flag("MOCK_TRACKTITAN")
MOCK_LMU: bool = _env_flag("MOCK_LMU")
MOCK_DROPBOX: bool = _env_flag("MOCK_DROPBOX")
SANDBOX_PATH = get_path(os.getenv("MOCK_BASE_PATH") or "sandbox")
SANDBOX_ENABLED: bool = MOCK_TRACKTITAN or MOCK_LMU or MOCK_DROPBOX

# Load db. A mock LMU install gets its own DB so sandbox runs never touch the
# record of what is really installed in the game. The real DB lives in the
# OS-standard per-user data directory (not next to the exe) so it survives
# version upgrades that extract to a fresh install folder.
if MOCK_LMU:
    DB_PATH = SANDBOX_PATH / "data" / "data.db"
else:
    DB_PATH = get_data_dir() / "data.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if not MOCK_LMU:
    # One-time migration: earlier versions stored the DB next to the exe
    # (BASE_DIR/data/hymo_lmu_sm.db, the old filename). Move it into the new
    # location (under the new data.db name) so an upgrade that extracts to a
    # fresh folder doesn't lose install history. No migration for the
    # hymo_lmu_sm.db -> data.db rename itself: a per-user DB already sitting at
    # get_data_dir()/hymo_lmu_sm.db from a recent release is simply left as-is.
    _legacy_db_path = get_path("data/hymo_lmu_sm.db")
    if _legacy_db_path.exists() and not DB_PATH.exists():
        shutil.move(str(_legacy_db_path), str(DB_PATH))
        print(f"[INFO] Migrated existing database to {DB_PATH}")

# ===== LOGGING CONFIG =====
_log_cfg = _config.get("logging", {})

# Console config
LOG_LEVEL_CONSOLE = _log_cfg.get("console", {}).get("level", "INFO")
LOG_FORMAT_CONSOLE = _log_cfg.get("console", {}).get("format", "%(message)s")

# File config
LOG_LEVEL_FILE = _log_cfg.get("file", {}).get("level", "DEBUG")
LOG_FORMAT_FILE = _log_cfg.get("file", {}).get("format", "%(asctime)s - %(levelname)s - %(message)s")

# ===== ENV =====
# All six secrets load unconditionally, whether present or not: the GUI's
# Settings tab is the only place that ever validates them (via
# check_credentials(), right before Start Download), never at import time.
# A real OS environment variable still wins over the DB-stored value (useful
# for CI/dev), same flexibility .env + load_dotenv gave before.
ACCESS_TOKEN_LIST: Optional[str] = os.getenv("ACCESS_TOKEN_LIST") or settings_db.get_secret("ACCESS_TOKEN_LIST")
ACCESS_TOKEN_DOWNLOAD: Optional[str] = os.getenv("ACCESS_TOKEN_DOWNLOAD") or settings_db.get_secret("ACCESS_TOKEN_DOWNLOAD")
USER_ID: Optional[str] = os.getenv("USER_ID") or settings_db.get_secret("USER_ID")

DROPBOX_APP_KEY: Optional[str] = os.getenv("DROPBOX_APP_KEY") or settings_db.get_secret("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET: Optional[str] = os.getenv("DROPBOX_APP_SECRET") or settings_db.get_secret("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN: Optional[str] = os.getenv("DROPBOX_REFRESH_TOKEN") or settings_db.get_secret("DROPBOX_REFRESH_TOKEN")

# ===== JSON =====
BASE_URL = _config["network"]["base_url"]
CONSUMER_ID = _config["network"]["consumer_id"]
PAGE_SIZE = _config["network"]["page_size"]
# Bounds of the minimum interval TrackTitanClient.throttle() keeps between two
# requests. Work done by the caller in between counts toward the interval.
MIN_DELAY: float = float(_config["network"]["min_delay"])
MAX_DELAY: float = float(_config["network"]["max_delay"])
if MAX_DELAY < MIN_DELAY:
    raise RuntimeError(f"network.max_delay ({MAX_DELAY}) must be >= network.min_delay ({MIN_DELAY})")
NETWORK_TIMEOUT: int = _config["network"].get("timeout", 30)

DOWNLOAD_PATH = get_path(_config["paths"]["download"]["base_path"])
CLEAN_DOWNLOAD = _config["paths"]["download"]["clean_download_after_copy"]

OVERWRITE : bool = _config["paths"]["setups"]["overwrite"]
DELETE_PREVIOUS_VERSION : bool = _config["paths"]["setups"]["delete_previous_version"]
LMU_SETUPS_BASE_PATH = get_path(_config["paths"]["setups"]["lmu_base_path"])

SETUP_FILE_EXTENSIONS: set[str] = {
    ext.lower()
    for ext in _config["paths"]["setups"]["file_extensions"]
}

REMOTE_TRACKS_ENABLED=_config["remote_tracks"]["enabled"]
REMOTE_TRACKS_TIMEOUT=_config["remote_tracks"]["timeout"]
REMOTE_TRACKS_URL=_config["remote_tracks"]["url"]

# ===== DROPBOX =====
_dropbox_cfg = _config.get("dropbox", {})
DROPBOX_FOLDER: str = _dropbox_cfg.get("folder", "/lmu-setups")
DROPBOX_TIMEOUT: int = _dropbox_cfg.get("timeout", 30)
# MASTER publishes packages from a worker pool of this size. 1 restores the
# fully serial behavior.
DROPBOX_UPLOAD_WORKERS: int = max(1, int(_dropbox_cfg.get("upload_workers", 4)))

# ===== UI =====
# The GUI's own persisted preferences: the dashboard language and whether the
# one-time HYMO warning dialog has already been dismissed.
_ui_cfg = _config.get("ui", {})
UI_LANGUAGE: str = _ui_cfg.get("language", "it")
UI_HYMO_WARNING_DISMISSED: bool = _ui_cfg.get("hymo_warning_dismissed", False)

# ===== SANDBOX PATHS =====
# Checked-in fixture catalog + zips that the mock TrackTitan client serves.
SANDBOX_TRACKTITAN_PATH = SANDBOX_PATH / "tracktitan"
# Local directory that stands in for the Dropbox share.
SANDBOX_DROPBOX_PATH = SANDBOX_PATH / "dropbox"

# A mock LMU install is just a real directory tree somewhere harmless, created
# up front so the GUI's own LMU_SETUPS_BASE_PATH.exists() check passes.
if MOCK_LMU:
    LMU_SETUPS_BASE_PATH = SANDBOX_PATH / "lmu" / "Settings"
    LMU_SETUPS_BASE_PATH.mkdir(parents=True, exist_ok=True)

# ===== Folders =====
Path(DOWNLOAD_PATH).mkdir(parents=True, exist_ok=True)


def check_credentials(mode: str, mock_tracktitan: bool, mock_dropbox: bool) -> list[str]:
    """Validate the secrets `mode` needs before a run can start.

    A required field must be present and at least as long as its entry in
    _MIN_CREDENTIAL_LENGTHS. Returns human-readable error strings; empty = OK.
    Called only by the GUI's Api.validate_start(), never at import time.
    """
    errors: list[str] = []

    def _require(value: Optional[str], label: str) -> None:
        if not value or len(value) < _MIN_CREDENTIAL_LENGTHS[label]:
            errors.append(f"Missing or invalid {label}")

    if mode in {"full", "master"} and not mock_tracktitan:
        _require(ACCESS_TOKEN_LIST, "ACCESS_TOKEN_LIST")
        _require(ACCESS_TOKEN_DOWNLOAD, "ACCESS_TOKEN_DOWNLOAD")
        _require(USER_ID, "USER_ID")

    if mode in {"master", "slave"} and not mock_dropbox:
        _require(DROPBOX_APP_KEY, "DROPBOX_APP_KEY")
        _require(DROPBOX_APP_SECRET, "DROPBOX_APP_SECRET")
        _require(DROPBOX_REFRESH_TOKEN, "DROPBOX_REFRESH_TOKEN")

    return errors


def save_env_values(values: dict[str, str]) -> None:
    """Persist secrets to settings.db, preserving every other key already there."""
    settings_db.save_secrets(values)


def save_config(patch: dict[str, Any]) -> None:
    """Deep-merge `patch` into settings.db's config row."""
    settings_db.save_config(patch)
