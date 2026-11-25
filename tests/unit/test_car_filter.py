"""Unit tests for the car filter: config default/merge, CarManager.is_car_selected,
the zip-name car-candidate parser, SlaveManager wiring and the GUI API."""
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import core.settings_db as settings_db


def _set_filter(all_cars: bool, selected: list[str]) -> None:
    settings_db.save_config({"cars": {"all": all_cars, "selected": selected}})


def _store_raw_config(data: dict) -> None:
    conn = settings_db._connect()
    with conn:
        conn.execute(
            "INSERT INTO config (id, data) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data = excluded.data",
            (json.dumps(data),),
        )
    conn.close()


# ----- config default + legacy merge ----------------------------------------


def test_default_config_has_cars_section_all_true():
    assert settings_db.DEFAULT_CONFIG["cars"] == {"all": True, "selected": []}
    assert settings_db.get_config()["cars"] == {"all": True, "selected": []}


def test_legacy_stored_row_without_cars_gets_the_default():
    _store_raw_config({"mode": "slave"})

    cfg = settings_db.get_config()

    assert cfg["mode"] == "slave"
    assert cfg["cars"] == {"all": True, "selected": []}


def test_partial_stored_cars_section_is_completed_by_defaults():
    _store_raw_config({"cars": {"selected": ["X"]}})
    assert settings_db.get_config()["cars"] == {"all": True, "selected": ["X"]}


def test_saving_selected_replaces_the_list_wholesale():
    _set_filter(False, ["A", "B"])
    _set_filter(False, ["C"])
    assert settings_db.get_config()["cars"]["selected"] == ["C"]


def test_config_module_exposes_the_filter_snapshot(load_config):
    cfg = load_config()
    assert cfg.CAR_FILTER_ALL is True
    assert cfg.CAR_FILTER_SELECTED == []


# ----- CarManager.is_car_selected -------------------------------------------


@pytest.fixture
def car_manager(minimal_cars_json, mocker):
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=minimal_cars_json)
    from processing.car_manager import CarManager
    return CarManager()


def test_default_selects_every_car_including_none(car_manager):
    assert car_manager.is_car_selected("Porsche 963") is True
    assert car_manager.is_car_selected("Whatever") is True
    assert car_manager.is_car_selected(None) is True


def test_all_true_ignores_the_selected_list(car_manager):
    _set_filter(True, ["Ferrari 499P"])
    assert car_manager.is_car_selected("Porsche 963") is True


def test_selected_membership(car_manager):
    _set_filter(False, ["Ferrari 499P"])
    assert car_manager.is_car_selected("Ferrari 499P") is True
    assert car_manager.is_car_selected("Porsche 963") is False


def test_membership_is_exact_not_case_insensitive(car_manager):
    _set_filter(False, ["Ferrari 499P"])
    assert car_manager.is_car_selected("ferrari 499p") is False


def test_none_name_is_not_selected_under_an_active_filter(car_manager):
    _set_filter(False, ["Ferrari 499P"])
    assert car_manager.is_car_selected(None) is False


def test_empty_selection_with_all_false_selects_nothing(car_manager):
    _set_filter(False, [])
    assert car_manager.is_car_selected("Ferrari 499P") is False


def test_settings_changes_are_reflected_live_without_a_new_manager(car_manager):
    assert car_manager.is_car_selected("Porsche 963") is True
    _set_filter(False, ["Ferrari 499P"])
    assert car_manager.is_car_selected("Porsche 963") is False
    _set_filter(False, ["Ferrari 499P", "Porsche 963"])
    assert car_manager.is_car_selected("Porsche 963") is True
    _set_filter(True, [])
    assert car_manager.is_car_selected("Porsche 963") is True


# ----- parse_remote_zip_car_candidates --------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("HYMO-Spa_Porsche_963_id1_1000.zip", ["Spa_Porsche_963", "Porsche_963", "963"]),
    ("HYMO-Spa_Ferrari499P_id1_1000.zip", ["Spa_Ferrari499P", "Ferrari499P"]),
    ("HYMO-Monza_Cadillac_V-Series.R_aaaa-bbbb_1700000000.zip",
     ["Monza_Cadillac_V-Series.R", "Cadillac_V-Series.R", "V-Series.R"]),
    ("hymo-Spa_Car_id1_5.zip", ["Spa_Car", "Car"]),
])
def test_candidates_are_underscore_suffixes_longest_first(name, expected):
    from domain.setup import parse_remote_zip_car_candidates
    assert parse_remote_zip_car_candidates(name) == expected


@pytest.mark.parametrize("name", [
    "Spa_Porsche_963_id1_1000.zip",   # no HYMO- prefix
    "HYMO-Spa_Porsche.zip",           # no id/ts
    "HYMO-x_y_id_notanumber.zip",
    "random.txt",
    "",
])
def test_candidates_empty_for_non_matching_names(name):
    from domain.setup import parse_remote_zip_car_candidates
    assert parse_remote_zip_car_candidates(name) == []


def test_candidates_single_segment_middle():
    from domain.setup import parse_remote_zip_car_candidates
    assert parse_remote_zip_car_candidates("HYMO-Solo_id1_1000.zip") == ["Solo"]


# ----- SlaveManager wiring (mocked) -----------------------------------------


def _meta(car="Porsche 963"):
    return {
        "id": "id1", "title": "T",
        "setupCombos": [{"car": {"name": car}, "track": {"name": "Spa"}}],
        "hotlapLink": None, "lastUpdatedAt": 1000, "isBundle": False,
    }


def _download(path_lower, local_path):
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(local, "w") as zf:
        zf.writestr("a.svm", b"svm")
        zf.writestr(".metadata.json", json.dumps(_meta()))
    return local


def _remote(name):
    from clients.dropbox_client import RemoteSetup
    return RemoteSetup(name=name, path_lower="/x/" + name.lower(), setup_id="id1", ts=1000)


@pytest.fixture
def sm(mocker, tmp_path):
    mocker.patch("orchestration.slave_manager.DOWNLOAD_PATH", tmp_path)
    from orchestration.slave_manager import SlaveManager
    dbx = MagicMock()
    setup_manager = MagicMock()
    cm = setup_manager.car_manager
    # Only the exact string "Porsche_963" resolves, so the candidate loop has
    # to walk past "Spa_Porsche_963" to reach it.
    cm.get_car_name.side_effect = lambda c, *_: "Porsche 963" if c in ("Porsche_963", "Porsche 963") else None
    cm.is_car_selected.return_value = True
    setup_manager.track_manager.get_track_folder_name.side_effect = lambda t: t
    setup_manager.track_manager.get_official_track_name.side_effect = lambda t: t
    database = MagicMock()
    database.is_installed_last_version.return_value = False
    dbx.download_to.side_effect = _download
    return SlaveManager(dropbox_client=dbx, setup_manager=setup_manager, database=database), dbx, setup_manager


def test_process_filtered_by_zip_name_car_does_not_download(sm):
    manager, dbx, setup_manager = sm
    setup_manager.car_manager.is_car_selected.return_value = False

    manager._process(_remote("HYMO-Spa_Porsche_963_id1_1000.zip"))

    setup_manager.car_manager.is_car_selected.assert_called_once_with("Porsche 963")
    dbx.download_to.assert_not_called()
    setup_manager.install_setup.assert_not_called()
    assert manager.unmatched.serialize() is None


def test_process_selected_car_still_installs(sm):
    manager, dbx, setup_manager = sm

    manager._process(_remote("HYMO-Spa_Porsche_963_id1_1000.zip"))

    dbx.download_to.assert_called_once()
    setup_manager.install_setup.assert_called_once()


def test_process_checks_each_distinct_resolved_car_then_metadata(sm):
    manager, dbx, setup_manager = sm
    manager._process(_remote("HYMO-Spa_Porsche_963_id1_1000.zip"))
    # One pre-download check (single distinct resolved car) + one post-metadata check.
    assert setup_manager.car_manager.is_car_selected.call_count == 2


def test_process_with_unresolvable_zip_name_and_no_filter_still_installs(sm):
    manager, dbx, setup_manager = sm
    setup_manager.car_manager.get_car_name.side_effect = lambda c, *_: "Porsche 963" if c == "Porsche 963" else None

    manager._process(_remote("HYMO-Spa_Weird_id1_1000.zip"))

    # Only the post-metadata check runs, on the official name.
    setup_manager.car_manager.is_car_selected.assert_called_once_with("Porsche 963")
    setup_manager.install_setup.assert_called_once()


def test_process_unresolvable_zip_name_filtered_after_metadata(sm, mocker):
    mocker.patch("orchestration.slave_manager.CLEAN_DOWNLOAD", True)
    manager, dbx, setup_manager = sm
    setup_manager.car_manager.get_car_name.side_effect = lambda c, *_: "Porsche 963" if c == "Porsche 963" else None
    setup_manager.car_manager.is_car_selected.return_value = False

    manager._process(_remote("HYMO-Spa_Weird_id1_1000.zip"))

    dbx.download_to.assert_called_once()
    setup_manager.car_manager.is_car_selected.assert_called_once_with("Porsche 963")
    setup_manager.install_setup.assert_not_called()
    assert manager.unmatched.serialize() is None
    local_zip = Path(dbx.download_to.call_args.args[1])
    assert not local_zip.exists()


def test_process_pre_check_never_skips_when_any_resolved_car_is_selected(sm):
    """A longer candidate can mis-resolve to another car via track text; the
    pre-download check must not skip as long as one resolved car is selected."""
    manager, dbx, setup_manager = sm
    setup_manager.car_manager.get_car_name.side_effect = lambda c, *_: {
        "Spa_Porsche_963": "Other Car",
        "Porsche_963": "Porsche 963",
        "Porsche 963": "Porsche 963",
    }.get(c)
    setup_manager.car_manager.is_car_selected.side_effect = lambda n: n == "Porsche 963"

    manager._process(_remote("HYMO-Spa_Porsche_963_id1_1000.zip"))

    dbx.download_to.assert_called_once()
    setup_manager.install_setup.assert_called_once()


def test_process_already_installed_skips_before_the_filter(sm):
    manager, dbx, setup_manager = sm
    manager.database.is_installed_last_version.return_value = True
    manager._process(_remote("HYMO-Spa_Porsche_963_id1_1000.zip"))
    setup_manager.car_manager.is_car_selected.assert_not_called()


def test_process_go_filtered_does_not_download_nor_record_unmatched(sm):
    from domain.go_setup import RemoteGoSetup
    manager, dbx, setup_manager = sm
    setup_manager.car_manager.get_car_name.side_effect = lambda c, *_: c
    setup_manager.car_manager.is_car_selected.return_value = False

    manager._process_go(RemoteGoSetup(name="GO.zip", path_lower="/a/b/go.zip", car="Oreca 07", track="Imola"))

    dbx.download_to.assert_not_called()
    setup_manager.install_setup.assert_not_called()
    assert manager.unmatched.serialize() is None


def test_process_go_unmatched_car_is_recorded_before_the_filter_is_consulted(sm):
    from domain.go_setup import RemoteGoSetup
    manager, dbx, setup_manager = sm
    manager._process_go(RemoteGoSetup(name="GO.zip", path_lower="/a/b/go.zip", car="Nope", track="Imola"))
    setup_manager.car_manager.is_car_selected.assert_not_called()
    assert manager.unmatched.serialize() == {"tracks": [], "cars": ["Nope"]}


# ----- GUI API ---------------------------------------------------------------


@pytest.fixture
def api(mocker):
    from gui.api import Api
    a = Api()
    a._car_manager = MagicMock()
    a._car_manager.get_all_cars.return_value = [{"name": "Porsche 963", "carClass": "hypercar"}]
    mocker.patch.object(Api, "_reload_config")
    return a


def test_get_car_filter_defaults(api):
    assert api.get_car_filter() == {
        "all": True, "selected": [], "cars": [{"name": "Porsche 963", "carClass": "hypercar"}],
    }


def test_set_car_filter_persists_and_reloads(api):
    api.set_car_filter(False, ["Porsche 963"])

    assert settings_db.get_config()["cars"] == {"all": False, "selected": ["Porsche 963"]}
    api._reload_config.assert_called_once()
    got = api.get_car_filter()
    assert got["all"] is False and got["selected"] == ["Porsche 963"]


def test_set_car_filter_dedups_preserving_order(api):
    api.set_car_filter(False, ["B", "A", "B", "A", "C"])
    assert settings_db.get_config()["cars"]["selected"] == ["B", "A", "C"]


def test_set_car_filter_overwrites_previous_selection(api):
    api.set_car_filter(False, ["A", "B"])
    api.set_car_filter(False, ["C"])
    assert api.get_car_filter()["selected"] == ["C"]


def test_set_car_filter_all_true_keeps_selection_stored(api):
    api.set_car_filter(True, ["A"])
    assert api.get_car_filter()["all"] is True
    assert api.get_car_filter()["selected"] == ["A"]


@pytest.mark.parametrize("all_cars", ["yes", 1, 0, None, "true"])
def test_set_car_filter_rejects_non_bool_all(api, all_cars):
    with pytest.raises(ValueError):
        api.set_car_filter(all_cars, [])
    assert settings_db.get_config()["cars"] == {"all": True, "selected": []}
    api._reload_config.assert_not_called()


@pytest.mark.parametrize("selected", ["Porsche 963", None, ("A",), {"A"}, [1], ["A", None], [["A"]]])
def test_set_car_filter_rejects_bad_selected(api, selected):
    with pytest.raises(ValueError):
        api.set_car_filter(False, selected)
    assert settings_db.get_config()["cars"] == {"all": True, "selected": []}
    api._reload_config.assert_not_called()


def test_set_car_filter_accepts_empty_list(api):
    api.set_car_filter(False, [])
    assert api.get_car_filter()["selected"] == []
    assert api.get_car_filter()["all"] is False
