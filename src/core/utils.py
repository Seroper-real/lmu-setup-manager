from pathlib import Path
import sys

import platformdirs

# The per-user data directory name.
APP_NAME = "lmu-setup-manager"

def get_base_dir() -> Path:
    # Case exe (PyInstaller)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]

BASE_DIR = get_base_dir()

def get_path(value: str | Path) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()

def get_data_dir() -> Path:
    # OS-standard per-user data directory (independent of where the app is
    # installed/extracted), so persistent data like the setups DB survives
    # version upgrades. A plain function, not a precomputed constant, so tests
    # can monkeypatch it the same way they patch BASE_DIR.
    return Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
