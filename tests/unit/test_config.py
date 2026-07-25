import pytest

from config_profiles import build_config


@pytest.fixture
def no_credentials(monkeypatch):
    for var in (
        "ACCESS_TOKEN_LIST", "ACCESS_TOKEN_DOWNLOAD", "USER_ID",
        "DROPBOX_APP_KEY", "DROPBOX_APP_SECRET", "DROPBOX_REFRESH_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)


def test_access_token_list():
    import core.config as config
    assert config.ACCESS_TOKEN_LIST == "test-token-list"


def test_access_token_download():
    import core.config as config
    assert config.ACCESS_TOKEN_DOWNLOAD == "test-token-download"


def test_user_id():
    import core.config as config
    assert config.USER_ID == "test-user-id"


def test_base_url_is_https():
    import core.config as config
    assert config.BASE_URL.startswith("https://")


def test_page_size_positive_int():
    import core.config as config
    assert isinstance(config.PAGE_SIZE, int)
    assert config.PAGE_SIZE > 0


def test_setup_file_extensions_format():
    import core.config as config
    assert isinstance(config.SETUP_FILE_EXTENSIONS, set)
    assert all(e.startswith(".") for e in config.SETUP_FILE_EXTENSIONS)


def test_go_setup_file_extensions():
    import core.config as config
    assert config.GO_SETUP_FILE_EXTENSIONS == {".svm", ".ld", ".ldx"}
    assert config.GO_SETUP_FILE_EXTENSIONS is not config.SETUP_FILE_EXTENSIONS


def test_mode_is_valid():
    import core.config as config
    assert config.MODE in {"full", "master", "slave"}


def test_dropbox_config_present():
    import core.config as config
    assert isinstance(config.DROPBOX_FOLDER, str)
    assert isinstance(config.DROPBOX_TIMEOUT, int)


def test_base_profile_has_no_sandbox_section():
    """The sandbox now lives in the environment, never in JSON."""
    assert "sandbox" not in build_config()


def test_profile_overlays_only_its_own_keys():
    merged = build_config("master")
    assert merged["mode"] == "master"
    # Untouched keys come through from the base.
    assert merged["network"]["page_size"] == 64


def test_unknown_profile_is_reported():
    with pytest.raises(FileNotFoundError, match="no-such-profile"):
        build_config("no-such-profile")


def test_sandbox_defaults_off_when_env_unset(load_config):
    cfg = load_config()
    assert cfg.MOCK_TRACKTITAN is False
    assert cfg.MOCK_LMU is False
    assert cfg.MOCK_DROPBOX is False
    assert cfg.SANDBOX_ENABLED is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_truthy_env_values_enable_a_mock(load_config, value):
    assert load_config(MOCK_TRACKTITAN=value).MOCK_TRACKTITAN is True


@pytest.mark.parametrize("value", ["0", "false", "", "maybe", "off"])
def test_non_truthy_env_values_leave_a_mock_off(load_config, value):
    assert load_config(MOCK_TRACKTITAN=value).MOCK_TRACKTITAN is False


def test_mock_tracktitan_waives_only_the_token_requirement(load_config, no_credentials):
    cfg = load_config(MOCK_TRACKTITAN="true")
    assert cfg.MOCK_TRACKTITAN is True
    assert cfg.MOCK_DROPBOX is False
    assert cfg.SANDBOX_ENABLED is True


def test_mock_dropbox_waives_credential_requirement(load_config, no_credentials):
    cfg = load_config("slave", MOCK_DROPBOX="true", MOCK_LMU="true")
    assert cfg.MOCK_DROPBOX is True


def test_mode_env_var_overrides_the_json(load_config):
    # config.test.json base carries mode "full".
    assert load_config().MODE == "full"
    assert load_config(MODE="master", MOCK_TRACKTITAN="true", MOCK_DROPBOX="true").MODE == "master"


def test_mock_lmu_redirects_lmu_and_db_paths(load_config, tmp_path):
    cfg = load_config(MOCK_LMU="true")

    sandbox_root = tmp_path / "sandbox"
    assert cfg.LMU_SETUPS_BASE_PATH == sandbox_root / "lmu" / "Settings"
    assert cfg.LMU_SETUPS_BASE_PATH.is_dir()
    assert cfg.DB_PATH == sandbox_root / "data" / "data.db"
    assert cfg.DB_PATH.parent.is_dir()


def test_mock_base_path_relocates_the_sandbox(load_config, tmp_path):
    root = tmp_path / "elsewhere"
    cfg = load_config(MOCK_LMU="true", MOCK_BASE_PATH=str(root))
    assert cfg.SANDBOX_PATH == root
    assert cfg.LMU_SETUPS_BASE_PATH == root / "lmu" / "Settings"


def test_without_mock_lmu_paths_are_real(load_config, tmp_path):
    cfg = load_config()
    assert cfg.LMU_SETUPS_BASE_PATH == tmp_path / "lmu"
    assert cfg.DB_PATH == tmp_path / "appdata" / "data.db"


def test_legacy_db_is_migrated_to_data_dir(load_config, tmp_path):
    # The old filename, from installs predating the hymo_lmu_sm.db -> data.db rename.
    legacy_db_path = tmp_path / "data" / "hymo_lmu_sm.db"
    legacy_db_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_db_path.write_bytes(b"legacy-db-contents")

    cfg = load_config()

    assert cfg.DB_PATH == tmp_path / "appdata" / "data.db"
    assert cfg.DB_PATH.read_bytes() == b"legacy-db-contents"
    assert not legacy_db_path.exists()


# --- check_credentials() rule matrix ----------------------------------------
# Nothing crashes at import time anymore (no_credentials no longer implies a
# SystemExit): check_credentials() is the only place these rules are enforced,
# and only when Api.validate_start() calls it.

_LONG = "x" * 25  # >= the 20-char threshold
_SHORT = "short"  # < the 20-char threshold


def test_check_credentials_passes_with_valid_full_creds(load_config, no_credentials):
    cfg = load_config(ACCESS_TOKEN_LIST=_LONG, ACCESS_TOKEN_DOWNLOAD=_LONG, USER_ID=_LONG)
    assert cfg.check_credentials("full", mock_tracktitan=False, mock_dropbox=False) == []


def test_check_credentials_fails_with_short_full_creds(load_config, no_credentials):
    cfg = load_config(ACCESS_TOKEN_LIST=_SHORT, ACCESS_TOKEN_DOWNLOAD=_SHORT, USER_ID=_SHORT)
    errors = cfg.check_credentials("full", mock_tracktitan=False, mock_dropbox=False)
    assert len(errors) == 3
    assert any("ACCESS_TOKEN_LIST" in e for e in errors)
    assert any("ACCESS_TOKEN_DOWNLOAD" in e for e in errors)
    assert any("USER_ID" in e for e in errors)


def test_check_credentials_full_waived_by_mock_tracktitan(load_config, no_credentials):
    cfg = load_config()
    assert cfg.check_credentials("full", mock_tracktitan=True, mock_dropbox=False) == []


def test_check_credentials_full_never_needs_dropbox(load_config, no_credentials):
    cfg = load_config(ACCESS_TOKEN_LIST=_LONG, ACCESS_TOKEN_DOWNLOAD=_LONG, USER_ID=_LONG)
    # Dropbox creds are absent, but "full" never checks them.
    assert cfg.check_credentials("full", mock_tracktitan=False, mock_dropbox=False) == []


def test_check_credentials_master_needs_both_unless_mocked(load_config, no_credentials):
    cfg = load_config(ACCESS_TOKEN_LIST=_LONG, ACCESS_TOKEN_DOWNLOAD=_LONG, USER_ID=_LONG)

    # TrackTitan creds are present and valid; Dropbox creds are still missing.
    errors = cfg.check_credentials("master", mock_tracktitan=False, mock_dropbox=False)
    assert len(errors) == 3
    assert all("DROPBOX" in e for e in errors)

    assert cfg.check_credentials("master", mock_tracktitan=False, mock_dropbox=True) == []
    assert cfg.check_credentials("master", mock_tracktitan=True, mock_dropbox=True) == []


def test_check_credentials_slave_only_needs_dropbox(load_config, no_credentials):
    cfg = load_config(
        "slave",
        DROPBOX_APP_KEY=_LONG, DROPBOX_APP_SECRET=_LONG, DROPBOX_REFRESH_TOKEN=_LONG,
    )
    # slave never checks TrackTitan tokens, mocked or not - passes despite no_credentials.
    assert cfg.check_credentials("slave", mock_tracktitan=False, mock_dropbox=False) == []


def test_check_credentials_slave_waived_by_mock_dropbox(load_config, no_credentials):
    cfg = load_config("slave")
    assert cfg.check_credentials("slave", mock_tracktitan=False, mock_dropbox=True) == []


@pytest.mark.parametrize("length,should_pass", [(19, False), (20, True), (25, True)])
def test_check_credentials_20_char_threshold(load_config, no_credentials, length, should_pass):
    token = "x" * length
    cfg = load_config(ACCESS_TOKEN_LIST=token, ACCESS_TOKEN_DOWNLOAD=token, USER_ID=token)
    errors = cfg.check_credentials("full", mock_tracktitan=False, mock_dropbox=False)
    assert (errors == []) is should_pass


@pytest.mark.parametrize("length,should_pass", [(14, False), (15, True), (25, True)])
def test_check_credentials_dropbox_app_key_secret_15_char_threshold(load_config, no_credentials, length, should_pass):
    # Dropbox's App Console issues app keys/secrets as real-world 15-character
    # strings (shorter than TrackTitan's tokens) - a real, correctly configured
    # value must not be rejected as "invalid". Regression test for the Slave
    # mode auth failure caused by a single 20-char threshold applied to every
    # credential.
    token = "x" * length
    cfg = load_config(
        "slave",
        DROPBOX_APP_KEY=token, DROPBOX_APP_SECRET=token, DROPBOX_REFRESH_TOKEN="x" * 64,
    )
    errors = cfg.check_credentials("slave", mock_tracktitan=False, mock_dropbox=False)
    assert (errors == []) is should_pass


def test_check_credentials_accepts_real_world_dropbox_app_key_secret_length(load_config, no_credentials):
    # The exact real-world shape reported in the Slave mode auth bug: 15-char
    # app key/secret plus a long refresh token, all otherwise valid.
    cfg = load_config(
        "slave",
        DROPBOX_APP_KEY="x" * 15, DROPBOX_APP_SECRET="x" * 15, DROPBOX_REFRESH_TOKEN="x" * 64,
    )
    assert cfg.check_credentials("slave", mock_tracktitan=False, mock_dropbox=False) == []


# --- save_env_values / save_config round-trips ------------------------------


def test_save_env_values_persists_a_new_secret(load_config):
    cfg = load_config()
    from core import settings_db
    assert settings_db.get_secret("USER_ID") is None

    cfg.save_env_values({"USER_ID": "some-user-id-1234567"})

    assert settings_db.get_secret("USER_ID") == "some-user-id-1234567"


def test_save_env_values_preserves_other_keys_on_update(load_config):
    cfg = load_config()
    cfg.save_env_values({"ACCESS_TOKEN_LIST": "first-value-1234567"})
    cfg.save_env_values({"USER_ID": "second-value-1234567"})

    from core import settings_db
    assert settings_db.get_secret("ACCESS_TOKEN_LIST") == "first-value-1234567"
    assert settings_db.get_secret("USER_ID") == "second-value-1234567"


def test_save_env_values_updates_an_existing_secret(load_config):
    cfg = load_config()
    cfg.save_env_values({"USER_ID": "old-value-1234567890"})
    cfg.save_env_values({"USER_ID": "new-value-1234567890"})

    from core import settings_db
    assert settings_db.get_secret("USER_ID") == "new-value-1234567890"


def test_save_config_deep_merge_preserves_sibling_keys(load_config):
    cfg = load_config()

    cfg.save_config({"ui": {"language": "en", "hymo_warning_dismissed": False}})
    cfg.save_config({"ui": {"hymo_warning_dismissed": True}})

    from core import settings_db
    after = settings_db.get_config()
    assert after["ui"]["hymo_warning_dismissed"] is True
    assert after["ui"]["language"] == "en"  # untouched by the second patch
    # Untouched top-level sections survive the merge too.
    assert after["network"]["page_size"] == 64
