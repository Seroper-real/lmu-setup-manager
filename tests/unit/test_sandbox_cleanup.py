from unittest.mock import MagicMock

from domain.setup import RemoteSetup
from orchestration.sandbox_cleanup import cleanup_sandbox_setups


def _remote(setup_id, name=None):
    return RemoteSetup(name=name or f"{setup_id}.zip", path_lower=f"/lmu-setups/{setup_id}.zip", setup_id=setup_id, ts=1)


def test_deletes_only_setups_matching_the_sandbox_ids():
    dbx = MagicMock()
    dbx.list_setups.return_value = [_remote("sandbox-1"), _remote("real-1"), _remote("sandbox-2")]
    dbx.delete_if_exists.return_value = True

    deleted = cleanup_sandbox_setups(dbx, {"sandbox-1", "sandbox-2"})

    assert deleted == 2
    dbx.delete_if_exists.assert_any_call("/lmu-setups/sandbox-1.zip")
    dbx.delete_if_exists.assert_any_call("/lmu-setups/sandbox-2.zip")
    assert dbx.delete_if_exists.call_count == 2


def test_never_touches_a_real_setup_not_in_the_sandbox_ids():
    dbx = MagicMock()
    dbx.list_setups.return_value = [_remote("real-1"), _remote("real-2")]

    deleted = cleanup_sandbox_setups(dbx, {"sandbox-1"})

    assert deleted == 0
    dbx.delete_if_exists.assert_not_called()


def test_a_setup_already_missing_on_dropbox_does_not_abort_the_rest():
    dbx = MagicMock()
    dbx.list_setups.return_value = [_remote("sandbox-1"), _remote("sandbox-2")]
    dbx.delete_if_exists.side_effect = [False, True]

    deleted = cleanup_sandbox_setups(dbx, {"sandbox-1", "sandbox-2"})

    assert deleted == 1
    assert dbx.delete_if_exists.call_count == 2


def test_empty_share_deletes_nothing():
    dbx = MagicMock()
    dbx.list_setups.return_value = []

    assert cleanup_sandbox_setups(dbx, {"sandbox-1"}) == 0
    dbx.delete_if_exists.assert_not_called()
