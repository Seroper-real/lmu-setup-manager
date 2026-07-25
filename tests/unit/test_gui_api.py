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
    setups = [_fake_installed(setup_id="1", track="Spa", track_found=True)]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("", False)

    assert result["totalCount"] == 1
    assert result["groups"][0]["track"] == "Spa"
    db_cls.assert_called_once()


def test_list_installed_setups_constructs_a_fresh_setupdb_per_call(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = []

    api.list_installed_setups("", False)
    api.list_installed_setups("", False)

    assert db_cls.call_count == 2


def test_list_installed_setups_groups_by_track(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    setups = [
        _fake_installed(setup_id="1", track="Spa", car="Porsche 963", track_found=True),
        _fake_installed(setup_id="2", track="Spa", car="BMW M4", track_found=True),
        _fake_installed(setup_id="3", track="Imola-HYMO", car="Ferrari 499P", track_found=False, matched_track_id=None),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("", False)

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
    setups = [
        _fake_installed(setup_id="1", track="Bahrain - WEC", car="Porsche 963", track_found=True, matched_track_id="Bahrain"),
        _fake_installed(setup_id="2", track="Bahrain International Circuit", car="BMW M4", track_found=True, matched_track_id="Bahrain"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("", False)

    assert len(result["groups"]) == 1
    assert result["groups"][0]["track"] == "Bahrain"
    assert len(result["groups"][0]["cars"]) == 2


def test_list_installed_setups_unmapped_only_filters(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    setups = [
        _fake_installed(setup_id="1", track="Spa", track_found=True),
        _fake_installed(setup_id="2", track="Imola-HYMO", track_found=False, matched_track_id=None),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("", True)

    assert result["totalCount"] == 1
    assert result["groups"][0]["track"] == "Imola-HYMO"


def test_list_installed_setups_search_matches_track_or_car(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    setups = [
        _fake_installed(setup_id="1", track="Spa", car="Porsche 963", matched_track_id="Spa"),
        _fake_installed(setup_id="2", track="Imola", car="BMW M4", matched_track_id="Imola"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("bmw", False)

    assert result["totalCount"] == 1
    assert result["groups"][0]["track"] == "Imola"
    assert result["grandTotal"] == 2


def test_list_installed_setups_serializes_file_names(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    setups = [_fake_installed(setup_id="1", track="Spa", file_names=["a.svm", "b.svm"])]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("", False)

    assert result["groups"][0]["cars"][0]["types"][0]["setups"][0]["fileNames"] == ["a.svm", "b.svm"]


def test_list_installed_setups_serializes_setup_type(api, mocker):
    mocker.patch.object(api, "current_mode", return_value="full")
    setups = [
        _fake_installed(setup_id="1", track="Spa", setup_type="HYMO"),
        _fake_installed(setup_id="2", track="Spa", setup_type="GO"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("", False)

    car_group = result["groups"][0]["cars"][0]
    types = {ty["type"]: [s["setupId"] for s in ty["setups"]] for ty in car_group["types"]}
    assert types == {"HYMO": ["1"], "GO": ["2"]}


def test_list_installed_setups_nests_hymo_and_go_under_one_car(api, mocker):
    # A car with both a HYMO (TrackTitan) and a GO (third-party) setup installed
    # must collapse into a single car entry, not two duplicate car rows.
    mocker.patch.object(api, "current_mode", return_value="full")
    setups = [
        _fake_installed(setup_id="1", track="Spa", car="Porsche 963", setup_type="HYMO"),
        _fake_installed(setup_id="2", track="Spa", car="Porsche 963", setup_type="GO"),
        _fake_installed(setup_id="3", track="Spa", car="BMW M4", setup_type="HYMO"),
    ]
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = setups

    result = api.list_installed_setups("", False)

    cars = result["groups"][0]["cars"]
    assert [c["car"] for c in cars] == ["BMW M4", "Porsche 963"]
    porsche = next(c for c in cars if c["car"] == "Porsche 963")
    assert [ty["type"] for ty in porsche["types"]] == ["HYMO", "GO"]
    bmw = next(c for c in cars if c["car"] == "BMW M4")
    assert [ty["type"] for ty in bmw["types"]] == ["HYMO"]


def test_delete_setup_delegates_to_setup_manager(api, mocker):
    tm_cls = mocker.patch("processing.track_manager.TrackManager")
    sm_cls = mocker.patch("processing.setup_manager.SetupManager")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    sm_cls.return_value.delete_setup.return_value = True

    result = api.delete_setup("id-1")

    sm_cls.assert_called_once_with(track_manager=tm_cls.return_value, database=db_cls.return_value)
    sm_cls.return_value.delete_setup.assert_called_once_with("id-1")
    assert result == {"deleted": True}


def test_delete_setup_reports_when_nothing_was_found(api, mocker):
    mocker.patch("processing.track_manager.TrackManager")
    sm_cls = mocker.patch("processing.setup_manager.SetupManager")
    mocker.patch("domain.setup_db.SetupDb")
    sm_cls.return_value.delete_setup.return_value = False

    assert api.delete_setup("ghost") == {"deleted": False}


def test_delete_setups_deletes_each_id_and_counts_successes(api, mocker):
    tm_cls = mocker.patch("processing.track_manager.TrackManager")
    sm_cls = mocker.patch("processing.setup_manager.SetupManager")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    sm_cls.return_value.delete_setup.side_effect = [True, False, True]

    result = api.delete_setups(["id-1", "id-2", "id-3"])

    sm_cls.assert_called_once_with(track_manager=tm_cls.return_value, database=db_cls.return_value)
    sm_cls.return_value.delete_setup.assert_any_call("id-1")
    sm_cls.return_value.delete_setup.assert_any_call("id-2")
    sm_cls.return_value.delete_setup.assert_any_call("id-3")
    assert result == {"deletedCount": 2}


def test_delete_setups_handles_empty_list(api, mocker):
    mocker.patch("processing.track_manager.TrackManager")
    sm_cls = mocker.patch("processing.setup_manager.SetupManager")
    mocker.patch("domain.setup_db.SetupDb")

    assert api.delete_setups([]) == {"deletedCount": 0}
    sm_cls.return_value.delete_setup.assert_not_called()


def test_delete_all_setups_deletes_every_installed_setup(api, mocker):
    tm_cls = mocker.patch("processing.track_manager.TrackManager")
    sm_cls = mocker.patch("processing.setup_manager.SetupManager")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = [
        _fake_installed(setup_id="1"),
        _fake_installed(setup_id="2"),
        _fake_installed(setup_id="3"),
    ]
    sm_cls.return_value.delete_setup.side_effect = [True, False, True]

    result = api.delete_all_setups()

    sm_cls.assert_called_once_with(track_manager=tm_cls.return_value, database=db_cls.return_value)
    sm_cls.return_value.delete_setup.assert_any_call("1")
    sm_cls.return_value.delete_setup.assert_any_call("2")
    sm_cls.return_value.delete_setup.assert_any_call("3")
    assert result == {"deletedCount": 2}


def test_delete_all_setups_handles_nothing_installed(api, mocker):
    mocker.patch("processing.track_manager.TrackManager")
    sm_cls = mocker.patch("processing.setup_manager.SetupManager")
    db_cls = mocker.patch("domain.setup_db.SetupDb")
    db_cls.return_value.fetch_all_installed_setups.return_value = []

    assert api.delete_all_setups() == {"deletedCount": 0}
    sm_cls.return_value.delete_setup.assert_not_called()


def test_get_track_folder_options_delegates_to_track_manager(api, mocker):
    tm_cls = mocker.patch("processing.track_manager.TrackManager")
    tm_cls.return_value.get_known_folder_names.return_value = ["Imola", "Spa"]

    assert api.get_track_folder_options() == ["Imola", "Spa"]


def test_map_track_updates_refreshes_and_relocates(api, mocker):
    tm_cls = mocker.patch("processing.track_manager.TrackManager")
    tm_instance = tm_cls.return_value
    sm_cls = mocker.patch("processing.setup_manager.SetupManager")
    db_cls = mocker.patch("domain.setup_db.SetupDb")

    result = api.map_track("Imola - WEC", "Imola")

    tm_instance.add_or_update_mapping.assert_called_once_with("Imola - WEC", "Imola")
    tm_instance.refresh.assert_called_once()
    sm_cls.assert_called_once_with(track_manager=tm_instance, database=db_cls.return_value)
    sm_cls.return_value.update_tracks_not_found.assert_called_once()
    assert result == {}


# ----- validate_start / the 20-char credential rule -----------------------------

def _rule_based_check_credentials(mode: str, mock_tracktitan: bool, mock_dropbox: bool) -> list[str]:
    """Stands in for core.config.check_credentials (not on this branch yet): same
    20-char rule the plan specifies, so validate_start's plumbing can be verified."""
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


def test_validate_start_flags_short_credentials(api, mocker):
    import core.config as config
    mocker.patch.object(config, "ACCESS_TOKEN_LIST", "short")
    mocker.patch.object(config, "ACCESS_TOKEN_DOWNLOAD", "short")
    mocker.patch.object(config, "USER_ID", "short")
    mocker.patch.object(config, "MOCK_TRACKTITAN", False)
    mocker.patch.object(config, "MOCK_DROPBOX", False)
    mocker.patch.object(config, "MOCK_LMU", True)  # isolate this test to the credential rule
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    errors = api.validate_start("full")

    assert errors == ["ACCESS_TOKEN_LIST", "ACCESS_TOKEN_DOWNLOAD", "USER_ID"]


def test_validate_start_passes_with_credentials_at_least_20_chars(api, mocker):
    import core.config as config
    long_value = "x" * 20
    mocker.patch.object(config, "ACCESS_TOKEN_LIST", long_value)
    mocker.patch.object(config, "ACCESS_TOKEN_DOWNLOAD", long_value)
    mocker.patch.object(config, "USER_ID", long_value)
    mocker.patch.object(config, "MOCK_TRACKTITAN", False)
    mocker.patch.object(config, "MOCK_DROPBOX", False)
    mocker.patch.object(config, "MOCK_LMU", True)  # isolate this test to the credential rule
    mocker.patch("core.config.check_credentials", side_effect=_rule_based_check_credentials, create=True)

    assert api.validate_start("full") == []


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

def test_start_download_rejects_a_concurrent_start(api, mocker):
    started = threading.Event()
    release = threading.Event()

    def fake_run(log, on_progress=None, cancel_event=None):
        started.set()
        release.wait(2)

    mocker.patch.object(api, "_resolve_run_fn", return_value=fake_run)

    first = api.start_download("full")
    assert started.wait(2)
    second = api.start_download("full")

    release.set()
    api._thread.join(timeout=2)

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


def test_stop_download_sets_the_cancel_event(api):
    api._cancel_event = threading.Event()
    api.stop_download()
    assert api._cancel_event.is_set()


def test_stop_download_is_a_noop_before_any_start(api):
    api.stop_download()  # must not raise


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

def test_browse_lmu_folder_without_a_window_returns_none(api):
    assert api.browse_lmu_folder("C:/somewhere") is None


def test_browse_lmu_folder_uses_the_native_folder_dialog(api, mocker):
    import webview
    api._window = mocker.Mock()
    api._window.create_file_dialog.return_value = ("C:/Games/LMU",)

    result = api.browse_lmu_folder("C:/old")

    api._window.create_file_dialog.assert_called_once_with(webview.FileDialog.FOLDER, directory="C:/old")
    assert result == "C:/Games/LMU"


def test_browse_lmu_folder_returns_none_when_the_dialog_is_cancelled(api, mocker):
    api._window = mocker.Mock()
    api._window.create_file_dialog.return_value = None
    assert api.browse_lmu_folder("C:/old") is None


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


def test_dropbox_oauth_get_url_defaults_to_the_read_write_scope(api, mocker):
    from clients.dropbox_client import READ_WRITE_SCOPES
    get_url = mocker.patch("clients.dropbox_client.get_authorization_url", return_value="https://dropbox.com/authorize")
    api.dropbox_oauth_get_url("key", "secret")
    get_url.assert_called_once_with("key", "secret", scope=READ_WRITE_SCOPES)


def test_dropbox_oauth_get_url_requests_the_read_only_scope(api, mocker):
    from clients.dropbox_client import READ_ONLY_SCOPES
    get_url = mocker.patch("clients.dropbox_client.get_authorization_url", return_value="https://dropbox.com/authorize")
    api.dropbox_oauth_get_url("key", "secret", token_type="read_only")
    get_url.assert_called_once_with("key", "secret", scope=READ_ONLY_SCOPES)


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


def test_tracktitan_fetch_tokens_start_rejects_a_concurrent_start(api, mocker):
    started = threading.Event()
    release = threading.Event()

    def fake_run(child, cancel_event):
        started.set()
        release.wait(2)

    mocker.patch("gui.api.webview.create_window", return_value=mocker.MagicMock())
    mocker.patch.object(api, "_run_tracktitan_fetch", side_effect=fake_run)

    first = api.tracktitan_fetch_tokens_start()
    assert started.wait(2)
    second = api.tracktitan_fetch_tokens_start()

    release.set()
    api._tt_thread.join(timeout=2)

    assert first == {"started": True}
    assert second == {"started": False, "reason": "already-running"}


def test_tracktitan_fetch_tokens_cancel_sets_the_cancel_event(api):
    api._tt_cancel_event = threading.Event()
    api.tracktitan_fetch_tokens_cancel()
    assert api._tt_cancel_event.is_set()


def test_tracktitan_fetch_tokens_cancel_is_a_noop_before_any_start(api):
    api.tracktitan_fetch_tokens_cancel()  # must not raise


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


def test_close_tt_window_is_a_noop_without_a_window(api):
    api._close_tt_window()  # must not raise


def test_push_tracktitan_tokens_without_a_window_is_a_noop(api):
    api._push_tracktitan_tokens("ok", {"ACCESS_TOKEN_LIST": "x"})  # must not raise


def test_push_tracktitan_tokens_sends_the_expected_payload(api):
    api._window = SimpleNamespace(evaluate_js=lambda script: setattr(api, "_last_js", script))
    api._push_tracktitan_tokens("ok", {"ACCESS_TOKEN_LIST": "x"})

    assert "window.onTrackTitanTokens" in api._last_js
    assert '"ok": true' in api._last_js
    assert '"reason": "ok"' in api._last_js
    assert '"ACCESS_TOKEN_LIST": "x"' in api._last_js
