import json
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def local_manager(minimal_cars_json, mocker):
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=minimal_cars_json)
    from processing.car_manager import CarManager
    return CarManager()


def test_loads_local_mapping(local_manager):
    assert local_manager.get_car_name("Ferrari 499P") == "Ferrari 499P"


def test_get_car_name_matches_via_matcher_pattern(local_manager):
    assert local_manager.get_car_name("some 499p variant") == "Ferrari 499P"


def test_get_car_name_case_insensitive(local_manager):
    assert local_manager.get_car_name("FERRARI 499P") == "Ferrari 499P"


def test_get_car_name_strips_whitespace(local_manager):
    assert local_manager.get_car_name("  963  ") == "Porsche 963"


def test_get_car_name_not_found_returns_none(local_manager):
    assert local_manager.get_car_name("Unknown Car") is None


def test_invalid_regex_is_skipped(tmp_path, mocker):
    data = {
        "cars": [
            {"name": "Broken", "class": "hypercar", "matcher": ["["]},
            {"name": "Ferrari 499P", "class": "hypercar", "matcher": ["499p"]},
        ],
    }
    p = tmp_path / "mapping.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=p)

    from processing.car_manager import CarManager
    mgr = CarManager()

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


def test_refresh_picks_up_new_local_file_content(tmp_path, mocker):
    data = {"cars": [{"name": "Ferrari 499P", "class": "hypercar", "matcher": ["499p"]}]}
    p = tmp_path / "mapping.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=p)

    from processing.car_manager import CarManager
    mgr = CarManager()
    assert mgr.get_car_name("Porsche 963") is None

    data["cars"].append({"name": "Porsche 963", "class": "hypercar", "matcher": ["963"]})
    p.write_text(json.dumps(data), encoding="utf-8")
    mgr.refresh()

    assert mgr.get_car_name("Porsche 963") == "Porsche 963"
