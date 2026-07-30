import json
import re
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def local_manager(minimal_cars_json, mocker):
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=minimal_cars_json)
    from processing.car_manager import CarManager
    return CarManager()


@pytest.fixture
def mapping_path(tmp_path):
    return tmp_path / "mapping.json"


@pytest.fixture
def make_manager(mapping_path, mocker):
    """Build a CarManager from an ad-hoc mapping.json body, for tests that need
    data shapes beyond what minimal_cars_json/local_manager provides."""
    def _make(data):
        mapping_path.write_text(json.dumps(data), encoding="utf-8")
        mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
        mocker.patch("processing.car_manager.get_path", return_value=mapping_path)
        from processing.car_manager import CarManager
        return CarManager()
    return _make


@pytest.mark.parametrize("query,expected", [
    ("Ferrari 499P", "Ferrari 499P"),        # exact match
    ("some 499p variant", "Ferrari 499P"),   # matcher pattern
    ("FERRARI 499P", "Ferrari 499P"),        # case-insensitive
    ("  963  ", "Porsche 963"),              # whitespace stripped
])
def test_get_car_name_resolves_known_variants(local_manager, query, expected):
    assert local_manager.get_car_name(query) == expected


def test_get_car_name_not_found_returns_none(local_manager):
    assert local_manager.get_car_name("Unknown Car") is None


def test_invalid_regex_is_skipped(make_manager):
    mgr = make_manager({
        "cars": [
            {"name": "Broken", "class": "hypercar", "matcher": ["["]},
            {"name": "Ferrari 499P", "class": "hypercar", "matcher": ["499p"]},
        ],
    })

    assert mgr.get_car_name("Ferrari 499P") == "Ferrari 499P"
    assert mgr.get_car_name("Broken Car") is None


def _mock_remote(mocker, remote_data):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = remote_data
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", True)
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_TIMEOUT", 5)
    mocker.patch("processing.catalog_loader.requests.get", return_value=mock_resp)


def test_remote_preferred_over_local_when_reachable(minimal_cars_json, mocker):
    remote_data = {"cars": [{"name": "New Car", "class": "lmp3", "matcher": ["newcar"]}]}
    _mock_remote(mocker, remote_data)
    mocker.patch("processing.car_manager.get_path", return_value=minimal_cars_json)

    from processing.car_manager import CarManager
    mgr = CarManager()

    assert mgr.get_car_name("newcar variant") == "New Car"
    assert mgr.get_car_name("Ferrari 499P") is None


def test_remote_failure_falls_back_to_local(minimal_cars_json, mocker):
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", True)
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_TIMEOUT", 5)
    mocker.patch("processing.catalog_loader.requests.get", side_effect=ConnectionError("offline"))
    mocker.patch("processing.car_manager.get_path", return_value=minimal_cars_json)

    from processing.car_manager import CarManager
    mgr = CarManager()

    assert mgr.get_car_name("Ferrari 499P") == "Ferrari 499P"


def test_remote_malformed_falls_back_to_local(minimal_cars_json, mocker):
    # Valid JSON, but missing the "name" key every car entry needs - must not
    # crash, must fall back to the local bundled file instead.
    remote_data = {"cars": [{"class": "lmp3", "matcher": ["newcar"]}]}
    _mock_remote(mocker, remote_data)
    mocker.patch("processing.car_manager.get_path", return_value=minimal_cars_json)

    from processing.car_manager import CarManager
    mgr = CarManager()

    assert mgr.get_car_name("Ferrari 499P") == "Ferrari 499P"


def test_remote_disabled_uses_local(minimal_cars_json, mocker):
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=minimal_cars_json)

    from processing.car_manager import CarManager
    mgr = CarManager()

    assert mgr.get_car_name("Ferrari 499P") == "Ferrari 499P"


def test_no_local_no_remote_raises(tmp_path, mocker):
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=tmp_path / "nonexistent.json")

    from processing.car_manager import CarManager
    with pytest.raises(RuntimeError, match="No mapping file"):
        CarManager()


def test_remote_bootstraps_when_local_missing(tmp_path, mocker):
    remote_data = {"cars": [{"name": "Ferrari 499P", "class": "hypercar", "matcher": ["499p"]}]}
    _mock_remote(mocker, remote_data)
    mocker.patch("processing.car_manager.get_path", return_value=tmp_path / "mapping.json")

    from processing.car_manager import CarManager
    mgr = CarManager()

    assert mgr.get_car_name("Ferrari 499P") == "Ferrari 499P"


# --- get_car_class / get_all_cars -------------------------------------------


def test_get_car_class_normalizes_the_raw_mapping_json_value(local_manager):
    assert local_manager.get_car_class("Ferrari 499P") == "HYPERCAR"


def test_get_car_class_unknown_car_returns_none(local_manager):
    assert local_manager.get_car_class("Unknown Car") is None


def test_get_car_class_maps_every_known_raw_class(make_manager):
    mgr = make_manager({
        "cars": [
            {"name": "A", "class": "hypercar", "matcher": ["a"]},
            {"name": "B", "class": "lmgt3", "matcher": ["b"]},
            {"name": "C", "class": "lmgte", "matcher": ["c"]},
            {"name": "D", "class": "lmp2", "matcher": ["d"]},
            {"name": "E", "class": "lmp2 (elms)", "matcher": ["e"]},
            {"name": "F", "class": "lmp3", "matcher": ["f"]},
        ],
    })

    assert mgr.get_car_class("A") == "HYPERCAR"
    assert mgr.get_car_class("B") == "GT3"
    assert mgr.get_car_class("C") == "GTE"
    assert mgr.get_car_class("D") == "P2"
    assert mgr.get_car_class("E") == "P2"
    assert mgr.get_car_class("F") == "P3"


@pytest.mark.parametrize("cars_data,query", [
    ([{"name": "No Class", "matcher": ["noclass"]}], "No Class"),                            # missing class field
    ([{"name": "Weird", "class": "not-a-real-class", "matcher": ["weird"]}], "Weird"),        # unrecognized raw value
])
def test_get_car_class_returns_none_for_missing_or_unrecognized_class(make_manager, cars_data, query):
    mgr = make_manager({"cars": cars_data})

    assert mgr.get_car_class(query) is None


def test_get_class_rank_follows_the_fixed_class_order_regardless_of_file_order(make_manager):
    # The fixed order is Hypercar, LMP2 (ELMS), LMP2, LMP3, LMGT3, LMGTE - the
    # file below deliberately lists them in a different order, to prove the
    # rank doesn't just mirror file position.
    mgr = make_manager({
        "cars": [
            {"name": "GTE Car", "class": "lmgte", "matcher": ["gte"]},
            {"name": "GT3 Car", "class": "lmgt3", "matcher": ["gt3"]},
            {"name": "P3 Car", "class": "lmp3", "matcher": ["p3"]},
            {"name": "P2 Car", "class": "lmp2", "matcher": ["p2"]},
            {"name": "P2 ELMS Car", "class": "lmp2 (elms)", "matcher": ["p2elms"]},
            {"name": "Hyper Car", "class": "hypercar", "matcher": ["hyper"]},
        ],
    })

    assert mgr.get_class_rank("Hyper Car") == 0
    assert mgr.get_class_rank("P2 ELMS Car") == 1
    assert mgr.get_class_rank("P2 Car") == 2
    assert mgr.get_class_rank("P3 Car") == 3
    assert mgr.get_class_rank("GT3 Car") == 4
    assert mgr.get_class_rank("GTE Car") == 5


def test_get_class_rank_unknown_car_sorts_after_every_known_class(local_manager):
    assert local_manager.get_class_rank("Unknown Car") > local_manager.get_class_rank("Ferrari 499P")


def test_get_all_cars_preserves_mapping_json_order_and_includes_class(local_manager):
    assert local_manager.get_all_cars() == [
        {"name": "Ferrari 499P", "carClass": "HYPERCAR"},
        {"name": "Porsche 963", "carClass": "HYPERCAR"},
    ]


def test_refresh_picks_up_new_local_file_content(make_manager, mapping_path):
    data = {"cars": [{"name": "Ferrari 499P", "class": "hypercar", "matcher": ["499p"]}]}
    mgr = make_manager(data)
    assert mgr.get_car_name("Porsche 963") is None

    data["cars"].append({"name": "Porsche 963", "class": "hypercar", "matcher": ["963"]})
    mapping_path.write_text(json.dumps(data), encoding="utf-8")
    mgr.refresh()

    assert mgr.get_car_name("Porsche 963") == "Porsche 963"


# --- manual_mapping fallback layer / add_or_update_mapping ------------------
# Mirrors TrackManager's own DB-customization tests - same fallback layer,
# now shared by cars too (see processing.car_manager.CarManager).


def test_db_customization_used_when_file_has_no_match(local_manager):
    from core import settings_db
    # "Stuttgart GTP Racer" shares no substring with the file's "963"
    # pattern, so only the DB customization can resolve it.
    settings_db.upsert_manual_mapping("car", "Porsche 963", "Stuttgart GTP Racer")
    local_manager.refresh()

    assert local_manager.get_car_name("Stuttgart GTP Racer") == "Porsche 963"


def test_file_pattern_wins_over_conflicting_db_customization(local_manager):
    from core import settings_db
    # "Ferrari 499P" already matches the file's "499p" pattern - a DB
    # customization pointing it elsewhere must lose.
    settings_db.upsert_manual_mapping("car", "Porsche 963", "Ferrari 499P")
    local_manager.refresh()

    assert local_manager.get_car_name("Ferrari 499P") == "Ferrari 499P"


def test_neither_file_nor_db_match_returns_none(local_manager):
    from core import settings_db
    settings_db.upsert_manual_mapping("car", "SomeCar", "totally-unrelated-pattern")
    local_manager.refresh()

    assert local_manager.get_car_name("Unknown Car") is None


def test_add_or_update_mapping_appends_to_existing_entry(local_manager):
    local_manager.add_or_update_mapping("Porsche 963 GTP", "Porsche 963")

    from core import settings_db
    custom = settings_db.get_manual_mappings("car")
    porsche = next(c for c in custom if c["name"] == "Porsche 963")
    assert re.escape("Porsche 963 GTP") in porsche["matcher"].split("|")
    assert len([c for c in custom if c["name"] == "Porsche 963"]) == 1


def test_add_or_update_mapping_creates_new_entry_with_self_matching_pattern(local_manager):
    # "Custom GT" isn't a mapping.json car - unlike "Ferrari 499P", it can't
    # already resolve on its own, so the self-matching safeguard kicks in.
    local_manager.add_or_update_mapping("New Hypercar X", "Custom GT")

    from core import settings_db
    custom = settings_db.get_manual_mappings("car")
    entry = next(c for c in custom if c["name"] == "Custom GT")
    # Both the raw car's own pattern and a self-matching one for the official
    # name itself, same safeguard TrackManager.add_or_update_mapping uses.
    assert entry["matcher"] == "|".join([re.escape("New Hypercar X"), re.escape("Custom GT")])


def test_add_or_update_mapping_skips_self_match_when_target_already_resolves(local_manager):
    # "Ferrari 499P" already resolves via the file's own "499p" pattern - the
    # self-matching safeguard must not add it as an extra alternative on its
    # own matcher (that would incorrectly merge unrelated future corrections
    # onto the same target into one shared entry, e.g. mapping "Nordschleife"
    # onto an existing "Monza" must leave Monza's matcher as just
    # "Nordschleife", not "Nordschleife|Monza").
    local_manager.add_or_update_mapping("New Hypercar X", "Ferrari 499P")

    from core import settings_db
    custom = settings_db.get_manual_mappings("car")
    ferrari = next(c for c in custom if c["name"] == "Ferrari 499P")
    assert ferrari["matcher"] == re.escape("New Hypercar X")


def test_add_or_update_mapping_skips_duplicate_pattern_when_car_equals_name(local_manager):
    local_manager.add_or_update_mapping("Ferrari 499P", "Ferrari 499P")

    from core import settings_db
    custom = settings_db.get_manual_mappings("car")
    ferrari = next(c for c in custom if c["name"] == "Ferrari 499P")
    assert ferrari["matcher"] == re.escape("Ferrari 499P")


def test_add_or_update_mapping_needs_refresh_to_take_effect(local_manager):
    # "Stuttgart GTP Racer" shares no substring with the existing "963"
    # pattern, so it does not resolve before mapping it.
    assert local_manager.get_car_name("Stuttgart GTP Racer") is None

    local_manager.add_or_update_mapping("Stuttgart GTP Racer", "Porsche 963")
    # add_or_update_mapping only persists to the DB; in-memory patterns are
    # stale until refresh() rebuilds them.
    assert local_manager.get_car_name("Stuttgart GTP Racer") is None

    local_manager.refresh()
    assert local_manager.get_car_name("Stuttgart GTP Racer") == "Porsche 963"
