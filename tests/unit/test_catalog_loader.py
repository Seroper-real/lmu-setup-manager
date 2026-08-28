from unittest.mock import MagicMock

import pytest

import processing.catalog_loader as cl


@pytest.fixture(autouse=True)
def _clear_cache():
    # The session-wide autouse fixture in conftest already does this, but be
    # explicit here so these tests are order-independent when run alone.
    cl.invalidate_remote_catalog_cache()
    yield
    cl.invalidate_remote_catalog_cache()


def _ok_response(payload):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    return resp


def test_successful_fetch_is_cached_for_the_process(mocker):
    get = mocker.patch(
        "processing.catalog_loader.requests.get",
        return_value=_ok_response({"tracks": []}),
    )

    first = cl.load_remote_json("https://example.test/mapping.json", 5, "mapping")
    second = cl.load_remote_json("https://example.test/mapping.json", 5, "mapping")
    third = cl.load_remote_json("https://example.test/mapping.json", 5, "mapping")

    assert first == second == third == {"tracks": []}
    get.assert_called_once()


def test_invalidate_forces_a_fresh_fetch(mocker):
    get = mocker.patch(
        "processing.catalog_loader.requests.get",
        return_value=_ok_response({"tracks": []}),
    )

    cl.load_remote_json("https://example.test/mapping.json", 5, "mapping")
    cl.invalidate_remote_catalog_cache()
    cl.load_remote_json("https://example.test/mapping.json", 5, "mapping")

    assert get.call_count == 2


def test_failed_fetch_is_not_cached_and_is_retried(mocker):
    get = mocker.patch(
        "processing.catalog_loader.requests.get",
        side_effect=ConnectionError("offline"),
    )

    assert cl.load_remote_json("https://example.test/mapping.json", 5, "mapping") is None
    assert cl.load_remote_json("https://example.test/mapping.json", 5, "mapping") is None
    # No negative caching: every call retries until one succeeds.
    assert get.call_count == 2


def test_a_later_success_after_failures_then_freezes(mocker):
    get = mocker.patch("processing.catalog_loader.requests.get")
    get.side_effect = [
        ConnectionError("offline"),
        _ok_response({"tracks": [{"name": "X", "matcher": ["x"], "lmu_folder": "X"}]}),
    ]

    assert cl.load_remote_json("https://example.test/mapping.json", 5, "mapping") is None
    good = cl.load_remote_json("https://example.test/mapping.json", 5, "mapping")
    frozen = cl.load_remote_json("https://example.test/mapping.json", 5, "mapping")

    assert good == frozen
    assert good["tracks"][0]["name"] == "X"
    assert get.call_count == 2  # third call served from cache


def test_cache_is_keyed_by_url(mocker):
    get = mocker.patch(
        "processing.catalog_loader.requests.get",
        side_effect=lambda url, timeout: _ok_response({"url": url}),
    )

    a = cl.load_remote_json("https://example.test/a.json", 5, "mapping")
    b = cl.load_remote_json("https://example.test/b.json", 5, "mapping")

    assert a == {"url": "https://example.test/a.json"}
    assert b == {"url": "https://example.test/b.json"}
    assert get.call_count == 2
