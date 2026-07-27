import json
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
