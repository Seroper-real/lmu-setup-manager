import json
import sqlite3

from core import settings_db


def test_get_config_seeds_defaults_on_first_call():
    cfg = settings_db.get_config()
    assert cfg["mode"] == "full"
    assert cfg["ui"]["hymo_warning_dismissed"] is False


def test_get_config_is_idempotent_on_second_call():
    first = settings_db.get_config()
    second = settings_db.get_config()
    assert first == second


def test_manual_mappings_and_secrets_start_empty():
    assert settings_db.get_manual_mappings("track") == []
    assert settings_db.get_manual_mappings("car") == []
    assert settings_db.get_secret("USER_ID") is None


def test_save_config_deep_merges_onto_defaults():
    settings_db.save_config({"ui": {"language": "en"}})
    cfg = settings_db.get_config()
    assert cfg["ui"]["language"] == "en"
    assert cfg["ui"]["hymo_warning_dismissed"] is False  # untouched sibling
    assert cfg["mode"] == "full"  # untouched top-level section


def test_save_secrets_upserts_and_preserves_other_keys():
    settings_db.save_secrets({"ACCESS_TOKEN_LIST": "a"})
    settings_db.save_secrets({"USER_ID": "b"})
    assert settings_db.get_secret("ACCESS_TOKEN_LIST") == "a"
    assert settings_db.get_secret("USER_ID") == "b"

    settings_db.save_secrets({"ACCESS_TOKEN_LIST": "updated"})
    assert settings_db.get_secret("ACCESS_TOKEN_LIST") == "updated"
    assert settings_db.get_secret("USER_ID") == "b"


def test_upsert_manual_mapping_creates_new_entry():
    settings_db.upsert_manual_mapping("track", "Spa", "spa|francorchamps")
    assert settings_db.get_manual_mappings("track") == [
        {"name": "Spa", "matcher": r"spa\|francorchamps"}
    ]


def test_upsert_manual_mapping_appends_to_existing_entry():
    settings_db.upsert_manual_mapping("track", "Spa", "spa")
    settings_db.upsert_manual_mapping("track", "Spa", "francorchamps")

    tracks = settings_db.get_manual_mappings("track")
    assert len(tracks) == 1
    assert tracks[0]["matcher"] == "spa|francorchamps"


def test_upsert_manual_mapping_skips_duplicate_literal_pattern():
    settings_db.upsert_manual_mapping("track", "Spa", "spa")
    settings_db.upsert_manual_mapping("track", "Spa", "spa")

    tracks = settings_db.get_manual_mappings("track")
    assert len(tracks) == 1
    assert tracks[0]["matcher"] == "spa"


def test_manual_mappings_are_isolated_by_type():
    settings_db.upsert_manual_mapping("track", "Spa", "circuit de spa")
    settings_db.upsert_manual_mapping("car", "Spa", "not a track")  # same `name`, different `type`

    assert settings_db.get_manual_mappings("track") == [{"name": "Spa", "matcher": r"circuit\ de\ spa"}]
    assert settings_db.get_manual_mappings("car") == [{"name": "Spa", "matcher": "not\\ a\\ track"}]


def test_get_manual_mappings_preserves_insertion_order():
    settings_db.upsert_manual_mapping("track", "Second", "b")
    settings_db.upsert_manual_mapping("track", "First", "a")

    names = [t["name"] for t in settings_db.get_manual_mappings("track")]
    assert names == ["Second", "First"]


def test_reset_to_factory_defaults_clears_everything():
    settings_db.save_config({"ui": {"language": "en"}, "mode": "master"})
    settings_db.save_secrets({"USER_ID": "some-id"})
    settings_db.upsert_manual_mapping("track", "Spa", "spa")
    settings_db.upsert_manual_mapping("car", "Porsche 963", "963")

    settings_db.reset_to_factory_defaults()

    assert settings_db.get_config() == settings_db.DEFAULT_CONFIG
    assert settings_db.get_secret("USER_ID") is None
    assert settings_db.get_manual_mappings("track") == []
    assert settings_db.get_manual_mappings("car") == []


# --- legacy `tracks` table migration ---------------------------------------


def test_legacy_tracks_table_is_migrated_into_manual_mapping_and_dropped():
    # Seed a pre-manual_mapping settings.db by hand, as an old app version
    # would have left it - _isolate_settings_db (conftest.py) already points
    # SETTINGS_DB_PATH at a fresh per-test tmp_path, so this is the only DB
    # settings_db will ever open in this test.
    conn = sqlite3.connect(settings_db.SETTINGS_DB_PATH)
    try:
        conn.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY AUTOINCREMENT, lmu_folder_name TEXT NOT NULL, tt_patterns TEXT NOT NULL)")
        conn.execute("INSERT INTO tracks (lmu_folder_name, tt_patterns) VALUES (?, ?)", ("Spa", json.dumps(["spa", "francorchamps"])))
        conn.execute("INSERT INTO tracks (lmu_folder_name, tt_patterns) VALUES (?, ?)", ("Nurburgring", json.dumps(["nordschleife"])))
        conn.commit()
    finally:
        conn.close()

    tracks = settings_db.get_manual_mappings("track")
    by_name = {t["name"]: t["matcher"] for t in tracks}
    assert by_name == {"Spa": "spa|francorchamps", "Nurburgring": "nordschleife"}

    conn = sqlite3.connect(settings_db.SETTINGS_DB_PATH)
    try:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'tracks'").fetchone()
        assert exists is None
    finally:
        conn.close()
