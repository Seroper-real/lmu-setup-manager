import os
import sys
import json
import sqlite3
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch

# CRITICO: impostare prima di qualsiasi import da src/.
# core.config imports core.settings_db, which opens/seeds settings.db against
# core.utils.get_data_dir() at *first* import - and some test module elsewhere
# in the session imports core.config (directly or via domain.setup_db) at its
# own module level, i.e. during collection, before any fixture has a chance to
# run. Redirect get_data_dir() here, before that first import can happen,
# so collection never touches the developer's real %LOCALAPPDATA% settings.db.
_COLLECTION_DATA_DIR = Path(tempfile.mkdtemp(prefix="lmu-sm-test-appdata-"))
import core.utils as _utils
_utils.get_data_dir = lambda: _COLLECTION_DATA_DIR

from config_profiles import seed_test_settings_db

os.environ.setdefault("ACCESS_TOKEN_LIST", "test-token-list")
os.environ.setdefault("ACCESS_TOKEN_DOWNLOAD", "test-token-download")
os.environ.setdefault("USER_ID", "test-user-id")


# The MODE and sandbox switches config.py now reads from the environment. Cleared
# before every load_config() so a value exported in the developer's own shell can
# never leak into a test and make it pass for the wrong reason.
_SANDBOX_ENV = ("MOCK_TRACKTITAN", "MOCK_LMU", "MOCK_DROPBOX", "MOCK_BASE_PATH", "MODE")


@pytest.fixture
def load_config(tmp_path, monkeypatch):
    """Re-import config.py against tests/resources/config.test.json + profiles,
    seeded into a tmp settings.db instead of the real per-user one.

    Never reads the repo's own settings: developers flip settings while working,
    and a test must not break when they do. Keyword arguments set the MOCK_* / MODE
    environment variables config.py reads (e.g. MOCK_TRACKTITAN="true").
    """
    original_config = sys.modules.get("core.config")
    original_settings_db = sys.modules.get("core.settings_db")

    def _load(*profiles: str, **env: str):
        for name in _SANDBOX_ENV:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)

        import core.utils as utils
        monkeypatch.setattr(utils, "BASE_DIR", tmp_path)
        monkeypatch.setattr(utils, "get_data_dir", lambda: tmp_path / "appdata")

        # Both must be popped: core.settings_db.SETTINGS_DB_PATH is a module-level
        # constant computed once at import time, so it must be re-imported (fresh,
        # against the just-monkeypatched get_data_dir) before seeding or core.config
        # would read/write whatever tmp_path an earlier test left cached.
        sys.modules.pop("core.config", None)
        sys.modules.pop("core.settings_db", None)

        seed_test_settings_db(tmp_path / "appdata", *profiles)

        # input() would block on exit if something unexpected prompts.
        with patch("builtins.input", return_value=""):
            import core.config as config
            return config

    yield _load

    sys.modules.pop("core.config", None)
    sys.modules.pop("core.settings_db", None)
    # Assigning sys.modules[...] directly (bypassing the normal import machinery)
    # does not update the "core" package's own attribute, which import sets as a
    # side effect. Left stale, it would make `import core.x as y` (attribute lookup)
    # diverge from `from core.x import z` (sys.modules lookup) for the rest of the
    # test session, silently reading two different module objects.
    if original_config is not None:
        sys.modules["core.config"] = original_config
        sys.modules["core"].config = original_config
    if original_settings_db is not None:
        sys.modules["core.settings_db"] = original_settings_db
        sys.modules["core"].settings_db = original_settings_db


@pytest.fixture(scope="session", autouse=True)
def _patch_config_paths(tmp_path_factory):
    """Redirige DB_PATH e DOWNLOAD_PATH a directory temporanee per tutta la sessione."""
    tmp = tmp_path_factory.mktemp("data")
    import core.config as cfg
    cfg.DB_PATH = tmp / "test.db"
    cfg.DOWNLOAD_PATH = tmp / "downloads"
    cfg.DOWNLOAD_PATH.mkdir()
    yield


@pytest.fixture(autouse=True)
def _isolate_settings_db(tmp_path, monkeypatch):
    """Every test gets its own settings.db, so writes that go through
    core.settings_db directly (e.g. TrackManager.add_or_update_mapping, which
    doesn't go through the load_config fixture) never leak between tests via the
    shared collection-time temp dir set up at the top of this module."""
    import core.settings_db as settings_db
    monkeypatch.setattr(settings_db, "SETTINGS_DB_PATH", tmp_path / "settings.db")


@pytest.fixture(autouse=True)
def _reset_remote_catalog_cache():
    """catalog_loader caches a successful remote-mapping fetch for the whole
    process. Without a reset between tests, the first test that lets a real (or
    mocked-success) fetch through would freeze that payload for every later
    test - including the ones asserting on requests.get call counts / offline
    fallback in test_track_manager.py and test_car_manager.py."""
    import processing.catalog_loader as cl
    cl.invalidate_remote_catalog_cache()
    yield
    cl.invalidate_remote_catalog_cache()


@pytest.fixture
def in_memory_db():
    """SetupDb su SQLite :memory: — nessun file su disco, nessuna dipendenza da DB_PATH."""
    from domain.setup_db import SetupDb

    class InMemorySetupDb(SetupDb):
        def __init__(self):
            self.conn = sqlite3.connect(":memory:")
            self.create_tables()

    return InMemorySetupDb()


@pytest.fixture
def sample_setup_data():
    return {
        "id": "uuid-1234",
        "title": "My Fast Setup",
        "setupCombos": [{"car": {"name": "Porsche 963"}, "track": {"name": "Spa-Francorchamps"}}],
        "hotlapLink": "https://example.com/hotlap",
        "lastUpdatedAt": 1700000000,
        "isBundle": False,
    }


@pytest.fixture
def sample_setup(sample_setup_data):
    from domain.setup import Setup
    return Setup(sample_setup_data)


@pytest.fixture
def minimal_tracks_json(tmp_path):
    data = {
        "tracks": [
            {"name": "Spa", "matcher": ["spa|francorchamps"], "lmu_folder": "Spa"},
            {"name": "Imola", "matcher": ["imola"], "lmu_folder": "Imola"},
        ],
    }
    p = tmp_path / "mapping.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def minimal_cars_json(tmp_path):
    data = {
        "cars": [
            {"name": "Ferrari 499P", "class": "hypercar", "matcher": ["499p"]},
            {"name": "Porsche 963", "class": "hypercar", "matcher": ["963"]},
        ],
    }
    p = tmp_path / "mapping.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p
