from unittest.mock import MagicMock

from domain.go_setup import RemoteGoSetup
from domain.setup import RemoteSetup
from orchestration.sandbox_cleanup import cleanup_sandbox_go_setups, cleanup_sandbox_setups


def _remote(setup_id, name=None):
    return RemoteSetup(name=name or f"{setup_id}.zip", path_lower=f"/lmu-setups/{setup_id}.zip", setup_id=setup_id, ts=1)


def _go_remote(car, track, name):
    return RemoteGoSetup(name=name, path_lower=f"/lmu-setups/{car}/{track}/{name}".lower(), car=car, track=track)


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


# ----- cleanup_sandbox_go_setups --------------------------------------------


def test_go_cleanup_deletes_only_expected_path_and_sandbox_marker():
    dbx = MagicMock()
    dbx.list_go_setups.return_value = [
        _go_remote("Oreca_07", "Imola", "GO-SANDBOX-ORECA-07.zip"),
        _go_remote("Ferrari_499P", "Losail", "GO-REAL-USER-ARCHIVE.zip"),  # expected path, no marker
        _go_remote("Some_Real_Car", "Some_Real_Track", "GO-SANDBOX-LOOKALIKE.zip"),  # marker, wrong path
    ]
    dbx.delete_if_exists.return_value = True

    deleted = cleanup_sandbox_go_setups(dbx, {("Oreca_07", "Imola"), ("Ferrari_499P", "Losail")})

    assert deleted == 1
    dbx.delete_if_exists.assert_called_once_with("/lmu-setups/oreca_07/imola/go-sandbox-oreca-07.zip")


def test_go_cleanup_marker_match_is_case_insensitive():
    dbx = MagicMock()
    dbx.list_go_setups.return_value = [_go_remote("Oreca_07", "Imola", "GO-Sandbox-Oreca-07.zip")]
    dbx.delete_if_exists.return_value = True

    assert cleanup_sandbox_go_setups(dbx, {("Oreca_07", "Imola")}) == 1


def test_go_cleanup_a_go_archive_already_missing_does_not_abort_the_rest():
    dbx = MagicMock()
    dbx.list_go_setups.return_value = [
        _go_remote("Oreca_07", "Imola", "GO-SANDBOX-ORECA-07.zip"),
        _go_remote("Ferrari_499P", "Losail", "GO-SANDBOX-FERRARI-499P.zip"),
    ]
    dbx.delete_if_exists.side_effect = [False, True]

    deleted = cleanup_sandbox_go_setups(dbx, {("Oreca_07", "Imola"), ("Ferrari_499P", "Losail")})

    assert deleted == 1
    assert dbx.delete_if_exists.call_count == 2


def test_go_cleanup_empty_share_deletes_nothing():
    dbx = MagicMock()
    dbx.list_go_setups.return_value = []

    assert cleanup_sandbox_go_setups(dbx, {("Oreca_07", "Imola")}) == 0
    dbx.delete_if_exists.assert_not_called()
