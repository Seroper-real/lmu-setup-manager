import json
import re
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def local_manager(minimal_tracks_json, mocker):
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.track_manager.get_path", return_value=minimal_tracks_json)
    from processing.track_manager import TrackManager
    return TrackManager()


@pytest.fixture
def make_manager(tmp_path, mocker):
    """Build a TrackManager from an ad-hoc mapping.json body, for tests that need
    data shapes beyond what minimal_tracks_json/local_manager provides."""
    def _make(data):
        p = tmp_path / "mapping.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", False)
        mocker.patch("processing.track_manager.get_path", return_value=p)
        from processing.track_manager import TrackManager
        return TrackManager()
    return _make


@pytest.mark.parametrize("query,expected", [
    ("Spa-Francorchamps", "Spa"),               # exact match
    ("SPA-FRANCORCHAMPS", "Spa"),                # case-insensitive
    ("  Imola  ", "Imola"),                      # whitespace stripped
    ("Spa - WEC", "Spa"),                        # variant match
    ("Circuit de Spa-Francorchamps", "Spa"),     # partial match
])
def test_get_track_folder_name_resolves_known_variants(local_manager, query, expected):
    assert local_manager.get_track_folder_name(query) == expected


def test_get_track_folder_not_found_returns_none(local_manager):
    assert local_manager.get_track_folder_name("Unknown Circuit") is None


def test_get_track_folder_le_mans_variants(make_manager):
    mgr = make_manager({"tracks": [{"name": "Lemans", "matcher": ["mans"], "lmu_folder": "Lemans"}]})

    assert mgr.get_track_folder_name("Le Mans") == "Lemans"
    assert mgr.get_track_folder_name("Le Mans - WEC") == "Lemans"
    assert mgr.get_track_folder_name("Le Mans La Sarthe") == "Lemans"


def test_invalid_regex_is_skipped(make_manager):
    mgr = make_manager({
        "tracks": [
            {"name": "Broken", "matcher": ["["], "lmu_folder": "Broken"},
            {"name": "Imola", "matcher": ["imola"], "lmu_folder": "Imola"},
        ],
    })

    assert mgr.get_track_folder_name("Imola") == "Imola"
    assert mgr.get_track_folder_name("Broken Track") is None


def _mock_remote(mocker, remote_data):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = remote_data
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", True)
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_TIMEOUT", 5)
    mocker.patch("processing.catalog_loader.requests.get", return_value=mock_resp)


def test_remote_preferred_over_local_when_reachable(minimal_tracks_json, mocker):
    # No versioning anymore: remote wins whenever it's reachable. The bundled
    # local file is only a fallback, and is never written back to.
    remote_data = {"tracks": [{"name": "NewFolder", "matcher": ["new track"], "lmu_folder": "NewFolder"}]}
    _mock_remote(mocker, remote_data)
    mocker.patch("processing.track_manager.get_path", return_value=minimal_tracks_json)

    from processing.track_manager import TrackManager
    mgr = TrackManager()

    assert mgr.get_track_folder_name("New Track") == "NewFolder"
    saved = json.loads(minimal_tracks_json.read_text(encoding="utf-8"))
    assert saved["tracks"][0]["lmu_folder"] == "Spa"


def test_remote_failure_falls_back_to_local(minimal_tracks_json, mocker):
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", True)
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_TIMEOUT", 5)
    mocker.patch("processing.catalog_loader.requests.get", side_effect=ConnectionError("offline"))
    mocker.patch("processing.track_manager.get_path", return_value=minimal_tracks_json)

    from processing.track_manager import TrackManager
    mgr = TrackManager()

    assert mgr.get_track_folder_name("Spa-Francorchamps") == "Spa"


def test_remote_malformed_falls_back_to_local(minimal_tracks_json, mocker):
    # Valid JSON, but missing the "lmu_folder" key every track entry needs -
    # must not crash, must fall back to the local bundled file instead.
    remote_data = {"tracks": [{"name": "NewFolder", "matcher": ["new track"]}]}
    _mock_remote(mocker, remote_data)
    mocker.patch("processing.track_manager.get_path", return_value=minimal_tracks_json)

    from processing.track_manager import TrackManager
    mgr = TrackManager()

    assert mgr.get_track_folder_name("Spa-Francorchamps") == "Spa"
    assert mgr.get_track_folder_name("New Track") is None


def test_remote_disabled_uses_local(minimal_tracks_json, mocker):
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.track_manager.get_path", return_value=minimal_tracks_json)

    from processing.track_manager import TrackManager
    mgr = TrackManager()

    assert mgr.get_track_folder_name("Spa-Francorchamps") == "Spa"


def test_no_local_no_remote_raises(tmp_path, mocker):
    mocker.patch("processing.track_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.track_manager.get_path", return_value=tmp_path / "nonexistent.json")

    from processing.track_manager import TrackManager
    with pytest.raises(RuntimeError, match="No mapping file"):
        TrackManager()


def test_remote_bootstraps_when_local_missing(tmp_path, mocker):
    # No local file -> remote is used (there's nothing to fall back to).
    remote_data = {"tracks": [{"name": "Spa", "matcher": ["spa"], "lmu_folder": "Spa"}]}
    _mock_remote(mocker, remote_data)
    mocker.patch("processing.track_manager.get_path", return_value=tmp_path / "mapping.json")

    from processing.track_manager import TrackManager
    mgr = TrackManager()

    assert mgr.get_track_folder_name("Spa-Francorchamps") == "Spa"


# --- get_official_track_name: independent from get_track_folder_name -------


def test_get_official_track_name_matches_name_not_lmu_folder(make_manager):
    # `name` and `lmu_folder` are resolved independently, even when they differ.
    mgr = make_manager({"tracks": [{"name": "Spa-Francorchamps", "matcher": ["spa"], "lmu_folder": "Spa"}]})

    assert mgr.get_official_track_name("Spa - WEC") == "Spa-Francorchamps"
    assert mgr.get_track_folder_name("Spa - WEC") == "Spa"


def test_get_official_track_name_not_found_returns_none(local_manager):
    assert local_manager.get_official_track_name("Unknown Circuit") is None


def test_get_official_track_name_falls_back_to_custom_folder_name(local_manager):
    from core import settings_db
    settings_db.upsert_track_pattern("Nurburgring", re.escape("Nordschleife"))
    local_manager.refresh()

    # No distinct `name` exists for a user "Correggi" mapping - lmu_folder_name doubles as it.
    assert local_manager.get_official_track_name("Nordschleife") == "Nurburgring"


# --- get_known_folder_names / add_or_update_mapping / refresh --------------


def test_get_known_folder_names_sorted_and_deduped(local_manager):
    assert local_manager.get_known_folder_names() == ["Imola", "Spa"]


def test_add_or_update_mapping_appends_to_existing_entry(local_manager):
    local_manager.add_or_update_mapping("Spa 24h", "Spa")

    from core import settings_db
    custom = settings_db.get_custom_tracks()
    spa = next(t for t in custom if t["lmu_folder_name"] == "Spa")
    assert re.escape("Spa 24h") in spa["tt_patterns"]
    # No new entry was created for an lmu_folder_name that already existed.
    assert len([t for t in custom if t["lmu_folder_name"] == "Spa"]) == 1


def test_add_or_update_mapping_creates_new_entry(local_manager):
    local_manager.add_or_update_mapping("Monza Circuit", "Monza")

    from core import settings_db
    custom = settings_db.get_custom_tracks()
    monza = next(t for t in custom if t["lmu_folder_name"] == "Monza")
    # Both the raw track's own pattern and a self-matching one for the folder
    # name itself (see test_add_or_update_mapping_folder_name_resolves_to_itself).
    assert monza["tt_patterns"] == [re.escape("Monza Circuit"), re.escape("Monza")]
    # get_known_folder_names merges file-derived and DB-customization names.
    assert local_manager.get_known_folder_names() == ["Imola", "Monza", "Spa"]


def test_add_or_update_mapping_folder_name_resolves_to_itself(local_manager):
    # Picking an existing lmu_folder_name back out of get_known_folder_names()
    # (e.g. the Upload tab's Track dropdown) must resolve to that same folder,
    # not create a new "<folder> - HYMO" one.
    local_manager.add_or_update_mapping("Monza Circuit", "Monza")
    local_manager.refresh()

    assert local_manager.get_track_folder_name("Monza") == "Monza"


def test_add_or_update_mapping_skips_duplicate_pattern_when_track_equals_folder(local_manager):
    local_manager.add_or_update_mapping("Monza", "Monza")

    from core import settings_db
    custom = settings_db.get_custom_tracks()
    monza = next(t for t in custom if t["lmu_folder_name"] == "Monza")
    assert monza["tt_patterns"] == [re.escape("Monza")]


def test_refresh_picks_up_new_mapping(local_manager):
    # "Belgian National Circuit" shares no substring with the existing
    # "spa|francorchamps" pattern, so it does not resolve before mapping it.
    assert local_manager.get_track_folder_name("Belgian National Circuit") is None

    local_manager.add_or_update_mapping("Belgian National Circuit", "Spa")
    # add_or_update_mapping only persists to the DB; in-memory patterns are stale
    # until refresh() rebuilds them.
    assert local_manager.get_track_folder_name("Belgian National Circuit") is None

    local_manager.refresh()
    assert local_manager.get_track_folder_name("Belgian National Circuit") == "Spa"


# --- DB customization layer: additive, checked only after the file misses ---


def test_db_customization_used_when_file_has_no_match(local_manager):
    from core import settings_db
    settings_db.upsert_track_pattern("Nurburgring", re.escape("Nordschleife"))
    local_manager.refresh()

    assert local_manager.get_track_folder_name("Nordschleife") == "Nurburgring"


def test_file_pattern_wins_over_conflicting_db_customization(local_manager):
    from core import settings_db
    # "Spa-Francorchamps" already matches the file's "spa|francorchamps" pattern
    # for lmu_folder_name "Spa" - a DB customization pointing it elsewhere must lose.
    settings_db.upsert_track_pattern("WrongFolder", re.escape("Spa-Francorchamps"))
    local_manager.refresh()

    assert local_manager.get_track_folder_name("Spa-Francorchamps") == "Spa"


def test_neither_file_nor_db_match_returns_none(local_manager):
    from core import settings_db
    settings_db.upsert_track_pattern("SomeFolder", "totally-unrelated-pattern")
    local_manager.refresh()

    assert local_manager.get_track_folder_name("Unknown Circuit") is None
