import pytest
import requests as req
from unittest.mock import MagicMock

from core.errors import AuthError


@pytest.fixture
def client():
    from clients.track_titan_client import TrackTitanClient
    return TrackTitanClient()


def _ok(json_data=None):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = json_data or {}
    return m


def test_get_correct_url(client, mocker):
    mock_get = mocker.patch("clients.track_titan_client.requests.get", return_value=_ok())
    client.get("/v2/games/leMansUltimate/setups")
    url = mock_get.call_args.args[0]
    assert "/v2/games/leMansUltimate/setups" in url


def test_get_sends_list_token(client, mocker):
    mock_get = mocker.patch("clients.track_titan_client.requests.get", return_value=_ok())
    client.get("/some/path")
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "test-token-list"


def test_get_raises_on_http_error(client, mocker):
    m = MagicMock()
    m.raise_for_status.side_effect = req.HTTPError("404")
    mocker.patch("clients.track_titan_client.requests.get", return_value=m)
    with pytest.raises(req.HTTPError):
        client.get("/bad/path")


def test_get_returns_json(client, mocker):
    mocker.patch("clients.track_titan_client.requests.get", return_value=_ok({"key": "val"}))
    assert client.get("/path") == {"key": "val"}


@pytest.mark.parametrize("status", [401, 403])
def test_get_raises_auth_error_on_401_or_403(client, mocker, status):
    m = MagicMock()
    m.status_code = status
    m.raise_for_status.side_effect = req.HTTPError(str(status))
    mocker.patch("clients.track_titan_client.requests.get", return_value=m)
    with pytest.raises(AuthError) as exc_info:
        client.get("/bad/path")
    # code/status let the GUI render a localized message instead of str(exc).
    assert exc_info.value.code == "tracktitan"
    assert exc_info.value.status == status


def test_download_link_raises_auth_error_on_403(client, mocker):
    m = MagicMock()
    m.status_code = 403
    m.raise_for_status.side_effect = req.HTTPError("403")
    mocker.patch("clients.track_titan_client.requests.post", return_value=m)
    with pytest.raises(AuthError):
        client.download_link("any-id")


def test_download_link_posts_to_correct_url(client, mocker):
    mock_post = mocker.patch("clients.track_titan_client.requests.post", return_value=_ok({"url": "x"}))
    client.download_link("setup-uuid-999")
    url = mock_post.call_args.args[0]
    assert "setup-uuid-999" in url


def test_download_link_sends_download_token(client, mocker):
    mock_post = mocker.patch("clients.track_titan_client.requests.post", return_value=_ok({"url": "x"}))
    client.download_link("any-id")
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["authorization"] == "test-token-download"


def test_download_returns_response(client, mocker):
    mock_resp = _ok()
    mocker.patch("clients.track_titan_client.requests.get", return_value=mock_resp)
    assert client.download("https://cdn.example.com/file.zip") is mock_resp


def _fixed_interval(mocker, seconds):
    mocker.patch("clients.track_titan_client.MIN_DELAY", seconds)
    mocker.patch("clients.track_titan_client.MAX_DELAY", seconds)


def test_throttle_does_not_sleep_when_the_interval_already_elapsed(client, mocker):
    """The whole point of the min-interval throttle: whatever the caller did between
    two requests (extract, zip, upload to Dropbox) already spaced them out, so MASTER
    pays nothing on top of it."""
    _fixed_interval(mocker, 1.0)
    mock_sleep = mocker.patch("clients.track_titan_client.time.sleep")
    mocker.patch("clients.track_titan_client.time.monotonic", return_value=105.0)
    client._last_request_at = 100.0  # last request 5s ago, interval is 1s

    client.throttle()

    mock_sleep.assert_not_called()


def test_throttle_sleeps_only_the_remainder(client, mocker):
    _fixed_interval(mocker, 2.0)
    mock_sleep = mocker.patch("clients.track_titan_client.time.sleep")
    mocker.patch("clients.track_titan_client.time.monotonic", return_value=100.5)
    client._last_request_at = 100.0  # 0.5s of work done against a 2s interval

    client.throttle()

    assert mock_sleep.call_args.args[0] == pytest.approx(1.5)


def test_first_throttle_does_not_sleep(client, mocker):
    _fixed_interval(mocker, 1.0)
    mock_sleep = mocker.patch("clients.track_titan_client.time.sleep")

    client.throttle()

    mock_sleep.assert_not_called()


def test_target_interval_is_clamped_to_the_configured_bounds(client, mocker):
    mocker.patch("clients.track_titan_client.MIN_DELAY", 0.5)
    mocker.patch("clients.track_titan_client.MAX_DELAY", 1.5)

    mocker.patch("clients.track_titan_client.random.gauss", return_value=-999.0)
    assert client._target_interval() == 0.5

    mocker.patch("clients.track_titan_client.random.gauss", return_value=999.0)
    assert client._target_interval() == 1.5


def test_a_request_marks_the_throttle_clock(client, mocker):
    mocker.patch("clients.track_titan_client.requests.get", return_value=_ok())
    assert client._last_request_at == 0.0

    client.get("/path")

    assert client._last_request_at > 0.0


def test_a_failed_request_still_marks_the_throttle_clock(client, mocker):
    """A failure is still traffic: it must not reset the spacing to zero."""
    m = MagicMock()
    m.raise_for_status.side_effect = req.HTTPError("500")
    mocker.patch("clients.track_titan_client.requests.get", return_value=m)

    with pytest.raises(req.HTTPError):
        client.get("/path")

    assert client._last_request_at > 0.0


def test_requests_send_a_timeout(client, mocker):
    mock_get = mocker.patch("clients.track_titan_client.requests.get", return_value=_ok())
    mock_post = mocker.patch("clients.track_titan_client.requests.post", return_value=_ok({"url": "x"}))

    client.get("/path")
    client.download_link("any-id")
    client.download("https://cdn.example.com/file.zip")

    assert mock_get.call_args_list[0].kwargs["timeout"] > 0
    assert mock_get.call_args_list[1].kwargs["timeout"] > 0
    assert mock_post.call_args.kwargs["timeout"] > 0


# ----- extract_tokens_from_cookies (the GUI's automatic token-fetch flow) -------


def test_extract_tokens_from_cookies_matches_by_cognito_suffix():
    from clients.track_titan_client import extract_tokens_from_cookies

    cookies = {
        "CognitoIdentityServiceProvider.abc123.someuser.accessToken": "list-token-value",
        "CognitoIdentityServiceProvider.abc123.someuser.idToken": "download-token-value",
        "CognitoIdentityServiceProvider.abc123.LastAuthUser": "someuser",
    }

    assert extract_tokens_from_cookies(cookies) == {
        "ACCESS_TOKEN_LIST": "list-token-value",
        "ACCESS_TOKEN_DOWNLOAD": "download-token-value",
        "USER_ID": "someuser",
    }


def test_extract_tokens_from_cookies_ignores_unrelated_cookies():
    from clients.track_titan_client import extract_tokens_from_cookies

    cookies = {
        "CognitoIdentityServiceProvider.abc123.someuser.accessToken": "list-token-value",
        "CognitoIdentityServiceProvider.abc123.someuser.idToken": "download-token-value",
        "CognitoIdentityServiceProvider.abc123.LastAuthUser": "someuser",
        "_ga": "GA1.2.12345",
        "cookie-consent": "accepted",
    }

    assert extract_tokens_from_cookies(cookies) == {
        "ACCESS_TOKEN_LIST": "list-token-value",
        "ACCESS_TOKEN_DOWNLOAD": "download-token-value",
        "USER_ID": "someuser",
    }


def test_extract_tokens_from_cookies_returns_none_when_one_is_missing():
    from clients.track_titan_client import extract_tokens_from_cookies

    cookies = {
        "CognitoIdentityServiceProvider.abc123.someuser.accessToken": "list-token-value",
        "CognitoIdentityServiceProvider.abc123.someuser.idToken": "download-token-value",
        # no .LastAuthUser cookie - login not finished yet
    }

    assert extract_tokens_from_cookies(cookies) is None


def test_extract_tokens_from_cookies_returns_none_for_no_cookies():
    from clients.track_titan_client import extract_tokens_from_cookies

    assert extract_tokens_from_cookies({}) is None
