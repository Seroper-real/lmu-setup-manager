import pytest

_MOCK_ENV = ("MOCK_TRACKTITAN", "MOCK_LMU", "MOCK_DROPBOX", "MOCK_BASE_PATH", "MODE")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _MOCK_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def apply():
    from main import _apply_cli_env
    return _apply_cli_env


def test_no_flags_set_nothing(apply):
    import os
    apply([])
    assert all(name not in os.environ for name in _MOCK_ENV)


def test_sandbox_enables_all_three(apply):
    import os
    apply(["--sandbox"])
    assert os.environ["MOCK_TRACKTITAN"] == "true"
    assert os.environ["MOCK_LMU"] == "true"
    assert os.environ["MOCK_DROPBOX"] == "true"
    assert "MODE" not in os.environ


def test_individual_mock_flag(apply):
    import os
    apply(["--mock-tracktitan"])
    assert os.environ["MOCK_TRACKTITAN"] == "true"
    assert "MOCK_LMU" not in os.environ
    assert "MOCK_DROPBOX" not in os.environ


def test_mode_and_base_path(apply):
    import os
    apply(["--mode", "master", "--mock-base-path", "/tmp/sbx"])
    assert os.environ["MODE"] == "master"
    assert os.environ["MOCK_BASE_PATH"] == "/tmp/sbx"


@pytest.mark.parametrize("argv", [["--bogus"], ["--mode", "sideways"]])
def test_invalid_cli_input_is_a_usage_error(apply, argv):
    with pytest.raises(SystemExit):
        apply(argv)


def test_a_preexported_flag_survives_no_cli(apply, monkeypatch):
    import os
    monkeypatch.setenv("MOCK_DROPBOX", "true")
    apply([])
    # A flag only ever sets; it never clears an already-exported value.
    assert os.environ["MOCK_DROPBOX"] == "true"
