from core import settings_db


def test_get_config_seeds_defaults_on_first_call():
    cfg = settings_db.get_config()
    assert cfg["mode"] == "full"
    assert cfg["ui"]["hymo_warning_dismissed"] is False


def test_get_config_is_idempotent_on_second_call():
    first = settings_db.get_config()
    second = settings_db.get_config()
    assert first == second


def test_tracks_and_secrets_start_empty():
    assert settings_db.get_custom_tracks() == []
    assert settings_db.get_custom_folder_names() == []
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


def test_upsert_track_pattern_creates_new_entry():
    settings_db.upsert_track_pattern("Spa", "spa|francorchamps")
    assert settings_db.get_custom_tracks() == [
        {"lmu_folder_name": "Spa", "tt_patterns": ["spa|francorchamps"]}
    ]


def test_upsert_track_pattern_appends_to_existing_entry():
    settings_db.upsert_track_pattern("Spa", "spa")
    settings_db.upsert_track_pattern("Spa", "francorchamps")

    tracks = settings_db.get_custom_tracks()
    assert len(tracks) == 1
    assert tracks[0]["tt_patterns"] == ["spa", "francorchamps"]


def test_get_custom_tracks_preserves_insertion_order():
    settings_db.upsert_track_pattern("Second", "b")
    settings_db.upsert_track_pattern("First", "a")

    names = [t["lmu_folder_name"] for t in settings_db.get_custom_tracks()]
    assert names == ["Second", "First"]


def test_get_custom_folder_names_sorted_and_deduped():
    settings_db.upsert_track_pattern("Zeta", "z")
    settings_db.upsert_track_pattern("Alpha", "a")
    settings_db.upsert_track_pattern("Alpha", "a2")

    assert settings_db.get_custom_folder_names() == ["Alpha", "Zeta"]


def test_reset_to_factory_defaults_clears_everything():
    settings_db.save_config({"ui": {"language": "en"}, "mode": "master"})
    settings_db.save_secrets({"USER_ID": "some-id"})
    settings_db.upsert_track_pattern("Spa", "spa")

    settings_db.reset_to_factory_defaults()

    assert settings_db.get_config() == settings_db.DEFAULT_CONFIG
    assert settings_db.get_secret("USER_ID") is None
    assert settings_db.get_custom_tracks() == []
