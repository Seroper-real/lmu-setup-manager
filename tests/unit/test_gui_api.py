"""Unit tests for gui.api.Api, exercised as a plain Python object (no real OS window)."""
import threading
from types import SimpleNamespace

import pytest


def _fake_installed(**overrides):
    base = dict(
        setup_id="id-1",
        track="Spa",
        car="Porsche 963",
        install_date=1_700_000_000_000,
        hotlap_link=None,
        file_names=["a.svm"],
        installation_folder="Spa",
        installation_base_path="C:/lmu",
        track_found=True,
        matched_track_id="Spa",
        setup_type="HYMO",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def api():
    from gui.api import Api
    return Api()


@pytest.fixture
def managers(mocker):
    """The TrackManager/CarManager/SetupManager/SetupDb quartet that Api methods
    delegating to SetupManager (delete_setup*, restore_factory_settings, map_track,
    upload_manual_setup) all construct identically."""
    return SimpleNamespace(
        track_manager=mocker.patch("processing.track_manager.TrackManager"),
        car_manager=mocker.patch("processing.car_manager.CarManager"),
        setup_manager=mocker.patch("processing.setup_manager.SetupManager"),
        setup_db=mocker.patch("domain.setup_db.SetupDb"),
    )


# ----- mode ------------------------------------------------------------------

def test_current_mode_falls_back_to_config_mode(api, mocker):
    import core.config as config
    mocker.patch.object(config, "MODE", "slave")
    assert api.current_mode() == "slave"


def test_set_mode_overrides_and_persists(api, mocker):
    save_cfg = mocker.patch("core.config.save_config", create=True)
    api.set_mode("master")
    assert api.current_mode() == "master"
    save_cfg.assert_called_once_with({"mode": "master"})


def test_set_mode_override_wins_over_config_mode(api, mocker):
    import core.config as config
    mocker.patch.object(config, "MODE", "full")
    mocker.patch("core.config.save_config", create=True)
    api.set_mode("slave")
    assert api.current_mode() == "slave"


# ----- bootstrap ---------------------------------------------------------------

def test_get_bootstrap_shapes_payload(api, mocker, tmp_path):
    import core.config as config
    mocker.patch.object(config, "MODE", "full")
    mocker.patch.object(config, "MOCK_TRACKTITAN", False)
    mocker.patch.object(config, "MOCK_LMU", False)
    mocker.patch.object(config, "MOCK_DROPBOX", False)
    mocker.patch.object(config, "LMU_SETUPS_BASE_PATH", tmp_path)
    mocker.patch.object(config, "UI_LANGUAGE", "en", create=True)
    mocker.patch.object(config, "UI_HYMO_WARNING_DISMISSED", True, create=True)
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = []

    bootstrap = api.get_bootstrap()

    assert bootstrap["mode"] == "full"
    from core.version import APP_VERSION
    assert bootstrap["appVersion"] == APP_VERSION
    assert bootstrap["sandboxActive"] is False
    assert bootstrap["lmuPath"] == str(tmp_path)
    assert bootstrap["lmuPathExists"] is True
    assert bootstrap["installedAvailable"] is True
    assert bootstrap["installedCount"] == 0
    assert bootstrap["language"] == "en"
    assert bootstrap["hymoWarningDismissed"] is True
    assert set(bootstrap["env"].keys()) == {
        "ACCESS_TOKEN_LIST", "ACCESS_TOKEN_DOWNLOAD", "USER_ID",
        "DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN",
    }
    assert "network" in bootstrap["config"]
    assert "dropbox" in bootstrap["config"]


def test_get_bootstrap_flags_a_missing_lmu_path(api, mocker, tmp_path):
    # There is no headless abort left for a missing LMU folder (that gate used to
    # live in main._require_lmu_path, now deleted): the GUI is the only place this
    # is surfaced, via this flag, before the user is allowed to press Start.
    import core.config as config
    mocker.patch.object(config, "MODE", "full")
    mocker.patch.object(config, "LMU_SETUPS_BASE_PATH", tmp_path / "no-such-game")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = []

    bootstrap = api.get_bootstrap()

    assert bootstrap["lmuPathExists"] is False


def test_get_bootstrap_shows_db_in_master_mode(api, mocker, tmp_path):
    # DB_PATH is not mode-conditional, so master still reports whatever full/slave
    # runs installed on this machine, even though master itself never writes to it.
    import core.config as config
    mocker.patch.object(config, "MODE", "master")
    mocker.patch.object(config, "LMU_SETUPS_BASE_PATH", tmp_path)
    mocker.patch.object(config, "UI_LANGUAGE", "it", create=True)
    mocker.patch.object(config, "UI_HYMO_WARNING_DISMISSED", False, create=True)
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = [_fake_installed(setup_id="1")]

    bootstrap = api.get_bootstrap()

    assert bootstrap["installedAvailable"] is True
    assert bootstrap["installedCount"] == 1
    db_cls.assert_called_once()


# ----- setup installati tab -----------------------------------------------------

def test_list_installed_setups_available_in_master_mode(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="master")
    mocker.patch("processing.car_manager.CarManager")
    setups = [_fake_installed(setup_id="1", track="Spa", track_found=True)]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    assert result["totalCount"] == 1
    assert result["groups"][0]["track"] == "Spa"
    db_cls.assert_called_once()


def test_list_installed_setups_constructs_a_fresh_setupdb_per_call(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = []

    api.list_installed_setups("")
    api.list_installed_setups("")

    assert db_cls.call_count == 2


def test_list_installed_setups_reuses_the_cached_car_manager(api, mocker):
    # Unlike SetupDb above, CarManager is cached on the Api instance - a second
    # call must not re-parse (or re-fetch remotely) mapping.json.
    mocker.patch.object(api, "current_mode", return_value="full")
    cm_cls = mocker.patch("processing.car_manager.CarManager")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = [_fake_installed(setup_id="1")]

    api.list_installed_setups("")
    api.list_installed_setups("")

    cm_cls.assert_called_once()


def test_list_installed_setups_groups_by_track(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    setups = [
        _fake_installed(setup_id="1", track="Spa", car="Porsche 963", track_found=True),
        _fake_installed(setup_id="2", track="Spa", car="BMW M4", track_found=True),
        _fake_installed(setup_id="3", track="Imola-HYMO", car="Ferrari 499P", track_found=False, matched_track_id=None),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    assert result["totalCount"] == 3
    tracks = {g["track"] for g in result["groups"]}
    assert tracks == {"Spa", "Imola-HYMO"}
    spa_group = next(g for g in result["groups"] if g["track"] == "Spa")
    assert len(spa_group["cars"]) == 2
    assert spa_group["trackFound"] is True
    imola_group = next(g for g in result["groups"] if g["track"] == "Imola-HYMO")
    assert imola_group["trackFound"] is False
    assert imola_group["cars"][0]["types"][0]["setups"][0]["setupId"] == "3"


def test_list_installed_setups_groups_by_matched_track_id_across_raw_names(api, mocker):
    # TrackTitan exposes the same physical track under different raw names; both
    # resolve to the same matched_track_id and must collapse into one card.
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    setups = [
        _fake_installed(setup_id="1", track="Bahrain - WEC", car="Porsche 963", track_found=True, matched_track_id="Bahrain"),
        _fake_installed(setup_id="2", track="Bahrain International Circuit", car="BMW M4", track_found=True, matched_track_id="Bahrain"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    assert len(result["groups"]) == 1
    assert result["groups"][0]["track"] == "Bahrain"
    assert len(result["groups"][0]["cars"]) == 2


def test_list_installed_setups_search_matches_track_or_car(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    setups = [
        _fake_installed(setup_id="1", track="Spa", car="Porsche 963", matched_track_id="Spa"),
        _fake_installed(setup_id="2", track="Imola", car="BMW M4", matched_track_id="Imola"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("bmw")

    assert result["totalCount"] == 1
    assert result["groups"][0]["track"] == "Imola"
    assert result["grandTotal"] == 2


def test_list_installed_setups_serializes_file_names(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    setups = [_fake_installed(setup_id="1", track="Spa", file_names=["a.svm", "b.svm"])]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    assert result["groups"][0]["cars"][0]["types"][0]["setups"][0]["fileNames"] == ["a.svm", "b.svm"]


def test_list_installed_setups_serializes_setup_type(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    setups = [
        _fake_installed(setup_id="1", track="Spa", setup_type="HYMO"),
        _fake_installed(setup_id="2", track="Spa", setup_type="GO"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    car_group = result["groups"][0]["cars"][0]
    types = {ty["type"]: [s["setupId"] for s in ty["setups"]] for ty in car_group["types"]}
    assert types == {"HYMO": ["1"], "GO": ["2"]}


def test_list_installed_setups_preserves_an_unknown_setup_type_instead_of_dropping_it(api, mocker):
    # _group_by_car_and_type used to hardcode ("HYMO", "GO") and silently drop
    # any other setup_type value - it must now keep HYMO/GO first but still
    # surface anything else instead of discarding it.
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    setups = [
        _fake_installed(setup_id="1", track="Spa", car="Porsche 963", setup_type="GO"),
        _fake_installed(setup_id="2", track="Spa", car="Porsche 963", setup_type="HYMO"),
        _fake_installed(setup_id="3", track="Spa", car="Porsche 963", setup_type="MYSTERY"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    types = [ty["type"] for ty in result["groups"][0]["cars"][0]["types"]]
    assert types == ["HYMO", "GO", "MYSTERY"]


def test_list_installed_setups_nests_hymo_and_go_under_one_car(api, mocker):
    # A car with both a HYMO (TrackTitan) and a GO (third-party) setup installed
    # must collapse into a single car entry, not two duplicate car rows.
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.car_manager.CarManager")
    setups = [
        _fake_installed(setup_id="1", track="Spa", car="Porsche 963", setup_type="HYMO"),
        _fake_installed(setup_id="2", track="Spa", car="Porsche 963", setup_type="GO"),
        _fake_installed(setup_id="3", track="Spa", car="BMW M4", setup_type="HYMO"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    cars = result["groups"][0]["cars"]
    assert [c["car"] for c in cars] == ["BMW M4", "Porsche 963"]
    porsche = next(c for c in cars if c["car"] == "Porsche 963")
    assert [ty["type"] for ty in porsche["types"]] == ["HYMO", "GO"]
    bmw = next(c for c in cars if c["car"] == "BMW M4")
    assert [ty["type"] for ty in bmw["types"]] == ["HYMO"]


def test_list_installed_setups_includes_car_class_from_car_manager(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    cm_cls = mocker.patch("processing.car_manager.CarManager")
    cm_cls.return_value.get_car_class.return_value = "HYPERCAR"
    setups = [_fake_installed(setup_id="1", track="Spa", car="Porsche 963")]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("")

    assert result["groups"][0]["cars"][0]["carClass"] == "HYPERCAR"
    cm_cls.return_value.get_car_class.assert_called_once_with("Porsche 963")


# ----- get_car_options ------------------------------------------------------

def test_get_car_options_delegates_to_the_cached_car_manager(api, mocker):
    cm_cls = mocker.patch("processing.car_manager.CarManager")
    cm_cls.return_value.get_all_cars.return_value = [{"name": "Porsche 963", "carClass": "HYPERCAR"}]

    assert api.get_car_options() == [{"name": "Porsche 963", "carClass": "HYPERCAR"}]
    cm_cls.assert_called_once()


def test_reload_config_invalidates_the_cached_car_manager(api, mocker):
    cm_cls = mocker.patch("processing.car_manager.CarManager")
    mocker.patch("core.config.save_env_values", create=True)
    mocker.patch("core.config.save_config", create=True)
    mocker.patch("gui.api.importlib.reload")

    api.get_car_options()  # populates the cache
    api._reload_config()
    api.get_car_options()  # must rebuild, not reuse the pre-reload instance

    assert cm_cls.call_count == 2


def test_delete_setup_delegates_to_setup_manager(api, managers):
    managers.setup_manager.return_value.delete_setup.return_value = True

    result = api.delete_setup("id-1")

    managers.setup_manager.assert_called_once_with(
        track_manager=managers.track_manager.return_value,
        car_manager=managers.car_manager.return_value,
        database=managers.setup_db.return_value,
    )
    managers.setup_manager.return_value.delete_setup.assert_called_once_with("id-1")
    assert result == {"deleted": True}


def test_delete_setup_reports_when_nothing_was_found(api, managers):
    managers.setup_manager.return_value.delete_setup.return_value = False

    assert api.delete_setup("ghost") == {"deleted": False}


def test_delete_setups_deletes_each_id_and_counts_successes(api, managers):
    managers.setup_manager.return_value.delete_setup.side_effect = [True, False, True]

    result = api.delete_setups(["id-1", "id-2", "id-3"])

    managers.setup_manager.assert_called_once_with(
        track_manager=managers.track_manager.return_value,
        car_manager=managers.car_manager.return_value,
        database=managers.setup_db.return_value,
    )
    managers.setup_manager.return_value.delete_setup.assert_any_call("id-1")
    managers.setup_manager.return_value.delete_setup.assert_any_call("id-2")
    managers.setup_manager.return_value.delete_setup.assert_any_call("id-3")
    assert result == {"deletedCount": 2}


def test_delete_setups_handles_empty_list(api, managers):
    assert api.delete_setups([]) == {"deletedCount": 0}
    managers.setup_manager.return_value.delete_setup.assert_not_called()


def test_delete_all_setups_deletes_every_installed_setup(api, managers):
    managers.setup_db.return_value.fetch_all_installed_setups.return_value = [
        _fake_installed(setup_id="1"),
        _fake_installed(setup_id="2"),
        _fake_installed(setup_id="3"),
    ]
    managers.setup_manager.return_value.delete_setup.side_effect = [True, False, True]

    result = api.delete_all_setups()

    managers.setup_manager.assert_called_once_with(
        track_manager=managers.track_manager.return_value,
        car_manager=managers.car_manager.return_value,
        database=managers.setup_db.return_value,
    )
    managers.setup_manager.return_value.delete_setup.assert_any_call("1")
    managers.setup_manager.return_value.delete_setup.assert_any_call("2")
    managers.setup_manager.return_value.delete_setup.assert_any_call("3")
    assert result == {"deletedCount": 2}


def test_delete_all_setups_handles_nothing_installed(api, managers):
    managers.setup_db.return_value.fetch_all_installed_setups.return_value = []

    assert api.delete_all_setups() == {"deletedCount": 0}
    managers.setup_manager.return_value.delete_setup.assert_not_called()


def test_restore_factory_settings_deletes_installed_setups_and_resets_config(api, managers, mocker):
    managers.setup_db.return_value.fetch_all_installed_setups.return_value = [
        _fake_installed(setup_id="1"),
        _fake_installed(setup_id="2"),
        _fake_installed(setup_id="3"),
    ]
    managers.setup_manager.return_value.delete_setup.side_effect = [True, False, True]
    reset_defaults = mocker.patch("core.settings_db.reset_to_factory_defaults")
    reload_cfg = mocker.patch.object(api, "_reload_config")

    result = api.restore_factory_settings()

    managers.setup_manager.assert_called_once_with(
        track_manager=managers.track_manager.return_value,
        car_manager=managers.car_manager.return_value,
        database=managers.setup_db.return_value,
    )
    managers.setup_manager.return_value.delete_setup.assert_any_call("1")
    managers.setup_manager.return_value.delete_setup.assert_any_call("2")
    managers.setup_manager.return_value.delete_setup.assert_any_call("3")
    reset_defaults.assert_called_once()
    reload_cfg.assert_called_once()
    assert result == {"deletedCount": 2}


def test_restore_factory_settings_handles_nothing_installed(api, managers, mocker):
    managers.setup_db.return_value.fetch_all_installed_setups.return_value = []
    mocker.patch("core.settings_db.reset_to_factory_defaults")
    mocker.patch.object(api, "_reload_config")

    assert api.restore_factory_settings() == {"deletedCount": 0}
    managers.setup_manager.return_value.delete_setup.assert_not_called()


def test_get_track_folder_options_delegates_to_track_manager(api, mocker):
    tm_cls = mocker.patch("processing.track_manager.TrackManager")
    tm_cls.return_value.get_known_folder_names.return_value = ["Imola", "Spa"]

    assert api.get_track_folder_options() == ["Imola", "Spa"]


def test_map_track_updates_and_refreshes(api, managers):
    tm_instance = managers.track_manager.return_value

    result = api.map_track("Imola - WEC", "Imola")

    tm_instance.add_or_update_mapping.assert_called_once_with("Imola - WEC", "Imola")
    tm_instance.refresh.assert_called_once()
    assert result == {}


def test_map_car_updates_and_refreshes(api, managers):
    """Mirrors map_track above, for the car half of an "unmatched setups" dialog row."""
    cm_instance = managers.car_manager.return_value

    result = api.map_car("BMW GTLM Hybrid", "BMW M4")

    cm_instance.add_or_update_mapping.assert_called_once_with("BMW GTLM Hybrid", "BMW M4")
    cm_instance.refresh.assert_called_once()
    assert result == {}


# ----- manual mapping list/delete (Mappature manuali tab) ----------------------

def test_list_manual_mappings_combines_both_types(api, mocker):
    mocker.patch(
        "core.settings_db.get_manual_mappings",
        side_effect=lambda t: (
            [{"id": "t1", "name": "Spa", "matcher": "spa"}]
            if t == "track"
            else [{"id": "c1", "name": "Porsche 963", "matcher": "963"}]
        ),
    )

    result = api.list_manual_mappings()

    assert result == [
        {"id": "t1", "type": "track", "name": "Spa", "matcher": "spa"},
        {"id": "c1", "type": "car", "name": "Porsche 963", "matcher": "963"},
    ]


def test_delete_manual_mapping_refreshes_car_manager_when_type_car(api, managers, mocker):
    mocker.patch("core.settings_db.delete_manual_mapping", return_value="car")
    cm_instance = managers.car_manager.return_value

    result = api.delete_manual_mapping("some-id")

    cm_instance.refresh.assert_called_once()
    assert result == {"deleted": True}


def test_delete_manual_mapping_does_not_touch_car_manager_when_type_track(api, managers, mocker):
    mocker.patch("core.settings_db.delete_manual_mapping", return_value="track")

    result = api.delete_manual_mapping("some-id")

    managers.car_manager.return_value.refresh.assert_not_called()
    assert result == {"deleted": True}


def test_delete_manual_mapping_handles_missing_id(api, managers, mocker):
    mocker.patch("core.settings_db.delete_manual_mapping", return_value=None)

    result = api.delete_manual_mapping("does-not-exist")

    managers.car_manager.return_value.refresh.assert_not_called()
    assert result == {"deleted": False}


def test_delete_all_manual_mappings_refreshes_car_manager(api, managers, mocker):
    mocker.patch("core.settings_db.delete_all_manual_mappings", return_value=3)
    cm_instance = managers.car_manager.return_value

    result = api.delete_all_manual_mappings()

    cm_instance.refresh.assert_called_once()
    assert result == {"deletedCount": 3}


# ----- validate_start / the 20-char credential rule -----------------------------

def _rule_based_check_credentials(mode: str, mock_tracktitan: bool, mock_dropbox: bool) -> list[str]:
    """Stands in for core.config.check_credentials so these tests exercise only
    validate_start's own plumbing (mode/mock routing, error list passthrough) in
    isolation from check_credentials' own error-message wording, which has its
    own coverage in test_config.py."""
    import core.config as config

    errors: list[str] = []
    if mode in {"full", "master"} and not mock_tracktitan:
        for name in ("ACCESS_TOKEN_LIST", "ACCESS_TOKEN_DOWNLOAD", "USER_ID"):
            value = getattr(config, name, None)
            if not value or len(value) < 20:
                errors.append(name)
    if mode in {"master", "slave"} and not mock_dropbox:
        for name in ("DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"):
            value = getattr(config, name, None)
            if not value or len(value) < 20:
                errors.append(name)
    return errors


@pytest.mark.parametrize("credential_value,expected_errors", [
    ("short", ["ACCESS_TOKEN_LIST", "ACCESS_TOKEN_DOWNLOAD", "USER_ID"]),
    ("x" * 20, []),
])
def test_validate_start_flags_credentials_under_20_chars(api, mocker, credential_value, expected_errors):
    import core.config as config
    mocker.patch.object(config, "ACCESS_TOKEN_LIST", credential_value)
    mocker.patch.object(config, "ACCESS_TOKEN_DOWNLOAD", credential_value)
    mocker.patch.object(config, "USER_ID", credential_value)
    mocker.patch.object(config, "MOCK_TRACKTITAN", False)
    mocker.patch.object(config, "MOCK_DROPBOX", False)
    mocker.patch.object(config, "MOCK_LMU", True)  # isolate this test to the credential rule
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    assert api.validate_start("full") == expected_errors


def test_validate_start_waives_the_check_when_mocked(api, mocker):
    import core.config as config
    mocker.patch.object(config, "MOCK_TRACKTITAN", True)
    mocker.patch.object(config, "MOCK_DROPBOX", True)
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    assert api.validate_start("master") == []


def test_validate_start_checks_dropbox_for_slave_mode(api, mocker):
    import core.config as config
    mocker.patch.object(config, "DROPBOX_APP_KEY", "short")
    mocker.patch.object(config, "DROPBOX_APP_SECRET", "short")
    mocker.patch.object(config, "DROPBOX_REFRESH_TOKEN", "short")
    mocker.patch.object(config, "MOCK_DROPBOX", False)
    mocker.patch.object(config, "MOCK_LMU", True)  # isolate this test to the credential rule
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    errors = api.validate_start("slave")

    assert errors == ["DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN"]


# ----- validate_start / the LMU path rule ---------------------------------------
# Only Full and Slave install setups locally (Master only uploads to Dropbox), so
# only those two modes must fail validate_start over a missing LMU_SETUPS_BASE_PATH.


@pytest.mark.parametrize("mode", ["full", "slave"])
def test_validate_start_flags_missing_lmu_path(api, mocker, tmp_path, mode):
    import core.config as config
    mocker.patch.object(config, "MOCK_TRACKTITAN", True)
    mocker.patch.object(config, "MOCK_DROPBOX", True)
    mocker.patch.object(config, "MOCK_LMU", False)
    mocker.patch.object(config, "LMU_SETUPS_BASE_PATH", tmp_path / "does-not-exist")
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    assert api.validate_start(mode) == ["Invalid or missing LMU_PATH"]


@pytest.mark.parametrize("mode", ["full", "slave"])
def test_validate_start_passes_with_an_existing_lmu_path(api, mocker, tmp_path, mode):
    import core.config as config
    mocker.patch.object(config, "MOCK_TRACKTITAN", True)
    mocker.patch.object(config, "MOCK_DROPBOX", True)
    mocker.patch.object(config, "MOCK_LMU", False)
    mocker.patch.object(config, "LMU_SETUPS_BASE_PATH", tmp_path)
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    assert api.validate_start(mode) == []


def test_validate_start_ignores_lmu_path_for_master_mode(api, mocker, tmp_path):
    import core.config as config
    mocker.patch.object(config, "MOCK_TRACKTITAN", True)
    mocker.patch.object(config, "MOCK_DROPBOX", True)
    mocker.patch.object(config, "MOCK_LMU", False)
    mocker.patch.object(config, "LMU_SETUPS_BASE_PATH", tmp_path / "does-not-exist")
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    assert api.validate_start("master") == []


def test_validate_start_lmu_path_waived_by_mock_lmu(api, mocker, tmp_path):
    import core.config as config
    mocker.patch.object(config, "MOCK_TRACKTITAN", True)
    mocker.patch.object(config, "MOCK_DROPBOX", True)
    mocker.patch.object(config, "MOCK_LMU", True)
    mocker.patch.object(config, "LMU_SETUPS_BASE_PATH", tmp_path / "does-not-exist")
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    assert api.validate_start("full") == []


# ----- start/stop download + progress bridge ------------------------------------

def _start_download_concurrently(api, mocker, fake_run):
    mocker.patch.object(api, "_resolve_run_fn", return_value=fake_run)
    return lambda: api.start_download("full")


def _start_tracktitan_fetch_concurrently(api, mocker, fake_run):
    mocker.patch("gui.api.webview.create_window", return_value=mocker.MagicMock())
    mocker.patch.object(api, "_run_tracktitan_fetch", side_effect=fake_run)
    return lambda: api.tracktitan_fetch_tokens_start()


@pytest.mark.parametrize(
    "setup,thread_attr",
    [
        (_start_download_concurrently, "_thread"),
        (_start_tracktitan_fetch_concurrently, "_tt_thread"),
    ],
    ids=["start_download", "tracktitan_fetch_tokens_start"],
)
def test_concurrent_start_is_rejected_while_already_running(api, mocker, setup, thread_attr):
    started = threading.Event()
    release = threading.Event()

    def fake_run(*args, **kwargs):
        started.set()
        release.wait(2)

    start = setup(api, mocker, fake_run)

    first = start()
    assert started.wait(2)
    second = start()

    release.set()
    getattr(api, thread_attr).join(timeout=2)

    assert first == {"started": True}
    assert second == {"started": False, "reason": "already-running"}


def test_start_download_pushes_progress_events_to_the_window(api, mocker):
    from core.progress import ProgressEvent, ProgressKind

    api._window = mocker.Mock()

    def fake_run(log, on_progress=None, cancel_event=None):
        on_progress(ProgressEvent(kind=ProgressKind.START, title="hello"))

    mocker.patch.object(api, "_resolve_run_fn", return_value=fake_run)

    api.start_download("full")
    api._thread.join(timeout=2)

    assert api._running is False
    api._window.evaluate_js.assert_called_once()
    js_call = api._window.evaluate_js.call_args[0][0]
    assert "start" in js_call
    assert "hello" in js_call


def test_start_download_records_error_from_a_failing_run(api, mocker):
    def fake_run(log, on_progress=None, cancel_event=None):
        raise RuntimeError("boom")

    mocker.patch.object(api, "_resolve_run_fn", return_value=fake_run)

    api.start_download("full")
    api._thread.join(timeout=2)

    assert api._running is False
    assert api.get_status()["lastError"] == "boom"


def test_start_download_flags_an_auth_error_as_such(api, mocker):
    from core.errors import AuthError
    from core.progress import ProgressEvent, ProgressKind

    def fake_run(log, on_progress=None, cancel_event=None):
        raise AuthError("token expired")

    mocker.patch.object(api, "_resolve_run_fn", return_value=fake_run)
    push = mocker.patch.object(api, "_push_progress")

    api.start_download("full")
    api._thread.join(timeout=2)

    assert api.get_status()["lastError"] == "token expired"
    event = push.call_args[0][0]
    assert isinstance(event, ProgressEvent)
    assert event.kind == ProgressKind.ERROR
    assert event.is_auth_error is True
    assert event.error_code == "generic"
    assert event.error_status is None


def test_start_download_forwards_the_auth_error_code_and_status(api, mocker):
    # The GUI localizes this dialog from code/status, not the English str(exc)
    # - see authErrorBody() in app.js.
    from core.errors import AuthError
    from core.progress import ProgressEvent, ProgressKind

    def fake_run(log, on_progress=None, cancel_event=None):
        raise AuthError("TrackTitan authentication failed (HTTP 401).", code="tracktitan", status=401)

    mocker.patch.object(api, "_resolve_run_fn", return_value=fake_run)
    push = mocker.patch.object(api, "_push_progress")

    api.start_download("full")
    api._thread.join(timeout=2)

    event = push.call_args[0][0]
    assert isinstance(event, ProgressEvent)
    assert event.error_code == "tracktitan"
    assert event.error_status == 401


def test_push_progress_includes_the_auth_error_flag_in_the_js_payload(api, mocker):
    from core.progress import ProgressEvent, ProgressKind

    api._window = mocker.Mock()
    api._push_progress(ProgressEvent(
        kind=ProgressKind.ERROR, title="expired", is_auth_error=True, error_code="dropbox", error_status=None,
    ))

    js_call = api._window.evaluate_js.call_args[0][0]
    assert '"authError": true' in js_call
    assert '"errorCode": "dropbox"' in js_call


def test_push_progress_includes_the_unmatched_list_in_the_js_payload(api, mocker):
    from core.progress import ProgressEvent, ProgressKind

    api._window = mocker.Mock()
    api._push_progress(ProgressEvent(
        kind=ProgressKind.FINISH, title="Download completed",
        unmatched={"tracks": ["Mystery Circuit"], "cars": ["Mystery Car"]},
    ))

    js_call = api._window.evaluate_js.call_args[0][0]
    assert '"unmatched": {"tracks": ["Mystery Circuit"], "cars": ["Mystery Car"]}' in js_call


def test_push_progress_unmatched_defaults_to_null_in_the_js_payload(api, mocker):
    from core.progress import ProgressEvent, ProgressKind

    api._window = mocker.Mock()
    api._push_progress(ProgressEvent(kind=ProgressKind.FINISH, title="Download completed"))

    js_call = api._window.evaluate_js.call_args[0][0]
    assert '"unmatched": null' in js_call


@pytest.mark.parametrize(
    "attr,call",
    [
        ("_cancel_event", lambda api: api.stop_download()),
        ("_tt_cancel_event", lambda api: api.tracktitan_fetch_tokens_cancel()),
    ],
    ids=["stop_download", "tracktitan_fetch_tokens_cancel"],
)
def test_cancel_sets_the_event(api, attr, call):
    setattr(api, attr, threading.Event())
    call(api)
    assert getattr(api, attr).is_set()


@pytest.mark.parametrize(
    "call",
    [
        lambda api: api.stop_download(),
        lambda api: api.tracktitan_fetch_tokens_cancel(),
        lambda api: api._close_tt_window(),
        lambda api: api._push_tracktitan_tokens("ok", {"ACCESS_TOKEN_LIST": "x"}),
    ],
    ids=["stop_download", "tracktitan_fetch_tokens_cancel", "_close_tt_window", "_push_tracktitan_tokens"],
)
def test_noop_calls_do_not_raise_without_prior_state(api, call):
    call(api)  # must not raise


def test_get_status_default(api):
    assert api.get_status() == {"running": False, "lastError": None}


def test_resolve_run_fn_maps_every_mode(api):
    import main
    assert api._resolve_run_fn("full") is main.run_full
    assert api._resolve_run_fn("master") is main.run_master
    assert api._resolve_run_fn("slave") is main.run_slave


def test_resolve_run_fn_rejects_an_unknown_mode(api):
    with pytest.raises(ValueError):
        api._resolve_run_fn("sideways")


# ----- settings tab --------------------------------------------------------------

_FILE_DIALOG_CALLS = [
    pytest.param(lambda api, current: api.browse_lmu_folder(current), id="browse_lmu_folder"),
    pytest.param(lambda api, current: api.pick_setup_zip_file(), id="pick_setup_zip_file"),
]


@pytest.mark.parametrize("call", _FILE_DIALOG_CALLS)
def test_file_dialog_without_a_window_returns_none(api, call):
    assert call(api, "C:/somewhere") is None


@pytest.mark.parametrize("call", _FILE_DIALOG_CALLS)
def test_file_dialog_returns_none_when_the_dialog_is_cancelled(api, mocker, call):
    api._window = mocker.Mock()
    api._window.create_file_dialog.return_value = None
    assert call(api, "C:/old") is None


def test_browse_lmu_folder_uses_the_native_folder_dialog(api, mocker):
    import webview
    api._window = mocker.Mock()
    api._window.create_file_dialog.return_value = ("C:/Games/LMU",)

    result = api.browse_lmu_folder("C:/old")

    api._window.create_file_dialog.assert_called_once_with(webview.FileDialog.FOLDER, directory="C:/old")
    assert result == "C:/Games/LMU"


def test_pick_setup_zip_file_uses_the_native_file_dialog(api, mocker):
    import webview
    api._window = mocker.Mock()
    api._window.create_file_dialog.return_value = ("C:/setups/my-setup.zip",)

    result = api.pick_setup_zip_file()

    api._window.create_file_dialog.assert_called_once_with(webview.FileDialog.OPEN, file_types=("Zip files (*.zip)",))
    assert result == "C:/setups/my-setup.zip"


# ----- save_dropped_setup_file ------------------------------------------------

def test_save_dropped_setup_file_writes_the_decoded_bytes(api):
    import base64
    from pathlib import Path

    result = api.save_dropped_setup_file("my-setup.zip", base64.b64encode(b"zip bytes").decode())

    saved = Path(result)
    assert saved.exists()
    assert saved.read_bytes() == b"zip bytes"
    assert saved.name.endswith("my-setup.zip")


def test_save_dropped_setup_file_strips_any_path_from_the_file_name(api):
    import base64
    from pathlib import Path

    result = api.save_dropped_setup_file("../../evil.zip", base64.b64encode(b"x").decode())

    saved = Path(result)
    assert saved.name.endswith("evil.zip")
    assert ".." not in saved.parts


def test_save_dropped_setup_file_gives_each_call_a_distinct_path(api):
    import base64

    data = base64.b64encode(b"x").decode()
    assert api.save_dropped_setup_file("setup.zip", data) != api.save_dropped_setup_file("setup.zip", data)


# ----- upload_manual_setup ---------------------------------------------------

@pytest.mark.parametrize("mode,setup_type", [("full", "HYMO"), ("slave", "GO")])
def test_upload_manual_setup_installs_locally_outside_master_mode(api, managers, mocker, mode, setup_type):
    mocker.patch.object(api, "current_mode", return_value=mode)
    build_setup = mocker.patch("processing.manual_upload.build_manual_setup")
    install_locally = mocker.patch("processing.manual_upload.install_manual_setup_locally")
    upload_to_dropbox = mocker.patch("processing.manual_upload.upload_manual_setup_to_dropbox")

    result = api.upload_manual_setup("C:/a.zip", setup_type, "Spa", "Porsche 963")

    build_setup.assert_called_once_with("Spa", "Porsche 963")
    managers.setup_manager.assert_called_once_with(
        track_manager=managers.track_manager.return_value,
        car_manager=managers.car_manager.return_value,
        database=managers.setup_db.return_value,
    )
    install_locally.assert_called_once_with(managers.setup_manager.return_value, "C:/a.zip", build_setup.return_value, setup_type)
    upload_to_dropbox.assert_not_called()
    assert result == {"ok": True}


def test_upload_manual_setup_uploads_to_dropbox_in_master_mode(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="master")
    build_setup = mocker.patch("processing.manual_upload.build_manual_setup")
    install_locally = mocker.patch("processing.manual_upload.install_manual_setup_locally")
    upload_to_dropbox = mocker.patch("processing.manual_upload.upload_manual_setup_to_dropbox")
    dropbox_factory = mocker.patch("clients.protocols.build_dropbox_client")

    result = api.upload_manual_setup("C:/a.zip", "GO", "Spa", "Porsche 963")

    upload_to_dropbox.assert_called_once_with(dropbox_factory.return_value, "C:/a.zip", build_setup.return_value, "GO")
    install_locally.assert_not_called()
    assert result == {"ok": True}


def test_upload_manual_setup_reports_an_auth_error(api, mocker):
    from core.errors import AuthError
    mocker.patch.object(api, "current_mode", return_value="master")
    mocker.patch("processing.manual_upload.build_manual_setup")
    mocker.patch(
        "processing.manual_upload.upload_manual_setup_to_dropbox",
        side_effect=AuthError("Dropbox authentication failed.", code="dropbox"),
    )
    mocker.patch("clients.protocols.build_dropbox_client")

    result = api.upload_manual_setup("C:/a.zip", "HYMO", "Spa", "Porsche 963")

    assert result["ok"] is False
    assert result["authError"] is True
    assert result["errorCode"] == "dropbox"


def test_upload_manual_setup_reports_a_generic_error(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    mocker.patch("processing.manual_upload.build_manual_setup")
    mocker.patch("processing.manual_upload.install_manual_setup_locally", side_effect=ValueError("no setup files"))
    mocker.patch("processing.track_manager.TrackManager")
    mocker.patch("processing.car_manager.CarManager")
    mocker.patch("domain.setup_db.SetupDb")
    mocker.patch("processing.setup_manager.SetupManager")

    result = api.upload_manual_setup("C:/a.zip", "HYMO", "Spa", "Porsche 963")

    assert result == {"ok": False, "error": "no setup files", "authError": False}


def test_clean_dropbox_setups_deletes_every_remote_setup(api, mocker):
    client = mocker.Mock()
    client.list_setups.return_value = [SimpleNamespace(path_lower="/a.zip"), SimpleNamespace(path_lower="/b.zip")]
    client.list_go_setups.return_value = [SimpleNamespace(path_lower="/go/c.zip")]
    client.delete_if_exists.side_effect = [True, False, True]
    mocker.patch("clients.protocols.build_dropbox_client", return_value=client)

    result = api.clean_dropbox_setups()

    client.delete_if_exists.assert_any_call("/a.zip")
    client.delete_if_exists.assert_any_call("/b.zip")
    client.delete_if_exists.assert_any_call("/go/c.zip")
    assert result == {"ok": True, "deletedCount": 2}


def test_clean_dropbox_setups_prunes_empty_ancestor_folders_after_every_delete(api, mocker):
    """Pruning must run only after every zip is gone - a Track folder shared
    by two zips is not actually empty until the second delete happens too."""
    client = mocker.Mock()
    client.list_setups.return_value = [SimpleNamespace(path_lower="/Car/Track/a.zip")]
    client.list_go_setups.return_value = [SimpleNamespace(path_lower="/Car/Track/GO-b.zip")]
    client.delete_if_exists.return_value = True
    calls = []
    client.prune_empty_ancestor_folders.side_effect = lambda path: calls.append(("prune", path))
    client.delete_if_exists.side_effect = lambda path: calls.append(("delete", path)) or True
    mocker.patch("clients.protocols.build_dropbox_client", return_value=client)

    api.clean_dropbox_setups()

    delete_calls = [c for c in calls if c[0] == "delete"]
    prune_calls = [c for c in calls if c[0] == "prune"]
    assert len(delete_calls) == 2
    assert len(prune_calls) == 2
    # Every delete happens before any prune is attempted.
    assert calls.index(prune_calls[0]) > calls.index(delete_calls[-1])


def test_clean_dropbox_setups_pushes_live_progress_after_every_delete(api, mocker):
    client = mocker.Mock()
    client.list_setups.return_value = [SimpleNamespace(path_lower="/a.zip"), SimpleNamespace(path_lower="/b.zip")]
    client.list_go_setups.return_value = [SimpleNamespace(path_lower="/go/c.zip")]
    client.delete_if_exists.side_effect = [True, False, True]
    mocker.patch("clients.protocols.build_dropbox_client", return_value=client)
    push = mocker.patch.object(api, "_push_danger_progress")

    api.clean_dropbox_setups()

    # Only the two successful deletes count, in order, and the failed one
    # (delete_if_exists -> False) must not bump the count. A final push (still
    # carrying the last count) switches the busy dialog to the folder-cleanup
    # phase once every delete is done.
    assert [call.args[0] for call in push.call_args_list] == [1, 2, 2]
    assert push.call_args_list[-1].kwargs == {"phase": "cleaning_folders"}


def test_push_danger_progress_evaluates_js_with_the_deleted_count(api, mocker):
    api._window = mocker.Mock()

    api._push_danger_progress(3)

    js_call = api._window.evaluate_js.call_args[0][0]
    assert "onDangerProgress" in js_call
    assert "3" in js_call
    assert '"deleting"' in js_call


def test_push_danger_progress_evaluates_js_with_the_given_phase(api, mocker):
    api._window = mocker.Mock()

    api._push_danger_progress(5, phase="cleaning_folders")

    js_call = api._window.evaluate_js.call_args[0][0]
    assert "onDangerProgress" in js_call
    assert "5" in js_call
    assert '"cleaning_folders"' in js_call


def test_clean_dropbox_setups_reports_an_auth_error(api, mocker):
    from core.errors import AuthError
    client = mocker.Mock()
    client.list_setups.side_effect = AuthError("Dropbox authentication failed.", code="dropbox")
    mocker.patch("clients.protocols.build_dropbox_client", return_value=client)

    result = api.clean_dropbox_setups()

    assert result["ok"] is False
    assert result["authError"] is True
    assert result["errorCode"] == "dropbox"


def test_clean_dropbox_setups_reports_a_generic_error(api, mocker):
    mocker.patch("clients.protocols.build_dropbox_client", side_effect=RuntimeError("Missing Dropbox credentials"))

    result = api.clean_dropbox_setups()

    assert result == {"ok": False, "error": "Missing Dropbox credentials", "authError": False}


def test_save_settings_writes_both_stores_and_hot_reloads_config(api, mocker):
    save_env = mocker.patch("core.config.save_env_values", create=True)
    save_cfg = mocker.patch("core.config.save_config", create=True)
    reload_cfg = mocker.patch.object(api, "_reload_config")

    api.save_settings({"USER_ID": "abc"}, {"mode": "full"})

    save_env.assert_called_once_with({"USER_ID": "abc"})
    save_cfg.assert_called_once_with({"mode": "full"})
    reload_cfg.assert_called_once()


def test_save_settings_skips_empty_patches(api, mocker):
    save_env = mocker.patch("core.config.save_env_values", create=True)
    save_cfg = mocker.patch("core.config.save_config", create=True)
    mocker.patch.object(api, "_reload_config")

    api.save_settings({}, {})

    save_env.assert_not_called()
    save_cfg.assert_not_called()


def test_save_settings_reloads_config_even_with_empty_patches(api, mocker):
    mocker.patch("core.config.save_env_values", create=True)
    mocker.patch("core.config.save_config", create=True)
    reload_cfg = mocker.patch.object(api, "_reload_config")

    api.save_settings({}, {})

    reload_cfg.assert_called_once()


def test_reload_config_reloads_core_config_and_a_loaded_consumer_module(api, mocker):
    import core.config as real_config

    fake_module = mocker.Mock()
    mocker.patch.dict("sys.modules", {"orchestration.download_manager": fake_module})
    reload_mock = mocker.patch("gui.api.importlib.reload")

    api._reload_config()

    reloaded = [c.args[0] for c in reload_mock.call_args_list]
    assert reloaded[0] is real_config
    assert fake_module in reloaded


def test_reload_config_skips_modules_never_imported(api, mocker):
    import sys
    from gui.api import _HOT_RELOAD_MODULES

    saved = {name: sys.modules.pop(name) for name in _HOT_RELOAD_MODULES if name in sys.modules}
    reload_mock = mocker.patch("gui.api.importlib.reload")
    try:
        api._reload_config()
        assert reload_mock.call_count == 1  # only core.config
    finally:
        sys.modules.update(saved)


def test_set_language_persists_the_choice(api, mocker):
    save_cfg = mocker.patch("core.config.save_config", create=True)
    api.set_language("en")
    save_cfg.assert_called_once_with({"ui": {"language": "en"}})


def test_dismiss_hymo_warning_persists_the_flag(api, mocker):
    save_cfg = mocker.patch("core.config.save_config", create=True)
    api.dismiss_hymo_warning()
    save_cfg.assert_called_once_with({"ui": {"hymo_warning_dismissed": True}})


def test_open_external_link_uses_webbrowser(api, mocker):
    web_open = mocker.patch("webbrowser.open")
    api.open_external_link("https://example.com")
    web_open.assert_called_once_with("https://example.com")


# ----- Dropbox OAuth "no redirect" flow ------------------------------------------

def test_dropbox_oauth_get_url_returns_the_authorize_url(api, mocker):
    mocker.patch("clients.dropbox_client.get_authorization_url", return_value="https://dropbox.com/authorize")
    assert api.dropbox_oauth_get_url("key", "secret") == {"url": "https://dropbox.com/authorize"}


def test_dropbox_oauth_get_url_reports_failures(api, mocker):
    mocker.patch("clients.dropbox_client.get_authorization_url", side_effect=RuntimeError("bad app key"))
    assert api.dropbox_oauth_get_url("key", "secret") == {"error": "bad app key"}


@pytest.mark.parametrize(
    "call_kwargs,scope_name",
    [({}, "READ_WRITE_SCOPES"), ({"token_type": "read_only"}, "READ_ONLY_SCOPES")],
    ids=["defaults_to_read_write", "requests_read_only"],
)
def test_dropbox_oauth_get_url_requests_the_expected_scope(api, mocker, call_kwargs, scope_name):
    import clients.dropbox_client as dropbox_client
    expected_scope = getattr(dropbox_client, scope_name)
    get_url = mocker.patch("clients.dropbox_client.get_authorization_url", return_value="https://dropbox.com/authorize")
    api.dropbox_oauth_get_url("key", "secret", **call_kwargs)
    get_url.assert_called_once_with("key", "secret", scope=expected_scope)


def test_dropbox_oauth_exchange_code_returns_the_refresh_token(api, mocker):
    mocker.patch("clients.dropbox_client.exchange_authorization_code", return_value="the-refresh-token")
    result = api.dropbox_oauth_exchange_code("key", "secret", "code")
    assert result == {"refreshToken": "the-refresh-token"}


def test_dropbox_oauth_exchange_code_reports_failures(api, mocker):
    mocker.patch("clients.dropbox_client.exchange_authorization_code", side_effect=RuntimeError("invalid code"))
    result = api.dropbox_oauth_exchange_code("key", "secret", "code")
    assert result == {"error": "invalid code"}


# ----- TrackTitan automatic token fetch (a second window + cookie polling) ------

def test_tracktitan_fetch_tokens_start_opens_a_window_and_starts_polling(api, mocker):
    child = mocker.MagicMock()
    create_window = mocker.patch("gui.api.webview.create_window", return_value=child)
    run_fetch = mocker.patch.object(api, "_run_tracktitan_fetch")

    result = api.tracktitan_fetch_tokens_start()
    api._tt_thread.join(timeout=2)

    assert result == {"started": True}
    assert create_window.call_args.kwargs["url"] == "https://app.tracktitan.io"
    assert api._tt_window is child
    run_fetch.assert_called_once()
    assert run_fetch.call_args.args[0] is child


def test_tracktitan_fetch_tokens_cancel_destroys_the_window_immediately(api, mocker):
    child = mocker.MagicMock()
    api._tt_window = child
    api._tt_cancel_event = threading.Event()

    api.tracktitan_fetch_tokens_cancel()

    child.destroy.assert_called_once()
    assert api._tt_window is None


def _cognito_cookies():
    from http.cookies import SimpleCookie

    def cookie(name, value):
        c = SimpleCookie()
        c[name] = value
        return c

    return [
        cookie("CognitoIdentityServiceProvider.abc.someuser.accessToken", "list-token"),
        cookie("CognitoIdentityServiceProvider.abc.someuser.idToken", "download-token"),
        cookie("CognitoIdentityServiceProvider.abc.LastAuthUser", "someuser"),
    ]


def test_run_tracktitan_fetch_succeeds_once_all_three_cookies_appear(api):
    child = SimpleNamespace(get_cookies=lambda: _cognito_cookies(), destroy=lambda: None)

    result = {}

    def fake_push(reason, tokens):
        result["reason"] = reason
        result["tokens"] = tokens

    api._push_tracktitan_tokens = fake_push
    api._run_tracktitan_fetch(child, threading.Event())

    assert result["reason"] == "ok"
    assert result["tokens"] == {
        "ACCESS_TOKEN_LIST": "list-token",
        "ACCESS_TOKEN_DOWNLOAD": "download-token",
        "USER_ID": "someuser",
    }


def test_run_tracktitan_fetch_closes_the_window_on_success(api, mocker):
    child = mocker.MagicMock()
    child.get_cookies.return_value = _cognito_cookies()
    mocker.patch.object(api, "_push_tracktitan_tokens")

    api._run_tracktitan_fetch(child, threading.Event())

    child.destroy.assert_called_once()
    assert api._tt_window is None


def test_run_tracktitan_fetch_reports_cancelled_when_the_event_is_already_set(api, mocker):
    child = mocker.MagicMock()
    child.get_cookies.return_value = []
    push = mocker.patch.object(api, "_push_tracktitan_tokens")
    cancel_event = threading.Event()
    cancel_event.set()

    api._run_tracktitan_fetch(child, cancel_event)

    push.assert_called_once_with("cancelled", None)
    child.get_cookies.assert_not_called()


def test_run_tracktitan_fetch_treats_a_destroyed_window_as_cancelled(api, mocker):
    child = mocker.MagicMock()
    child.get_cookies.side_effect = Exception("window gone")
    push = mocker.patch.object(api, "_push_tracktitan_tokens")

    api._run_tracktitan_fetch(child, threading.Event())

    push.assert_called_once_with("cancelled", None)


def test_run_tracktitan_fetch_times_out_when_login_never_completes(api, mocker):
    mocker.patch.object(api, "_TT_TIMEOUT_SECONDS", 0)
    child = mocker.MagicMock()
    push = mocker.patch.object(api, "_push_tracktitan_tokens")

    api._run_tracktitan_fetch(child, threading.Event())

    child.get_cookies.assert_not_called()
    push.assert_called_once_with("timeout", None)


def test_close_tt_window_swallows_destroy_errors(api, mocker):
    child = mocker.MagicMock()
    child.destroy.side_effect = Exception("already closed")
    api._tt_window = child

    api._close_tt_window()  # must not raise

    assert api._tt_window is None


def test_push_tracktitan_tokens_sends_the_expected_payload(api):
    api._window = SimpleNamespace(evaluate_js=lambda script: setattr(api, "_last_js", script))
    api._push_tracktitan_tokens("ok", {"ACCESS_TOKEN_LIST": "x"})

    assert "window.onTrackTitanTokens" in api._last_js
    assert '"ok": true' in api._last_js
    assert '"reason": "ok"' in api._last_js
    assert '"ACCESS_TOKEN_LIST": "x"' in api._last_js
