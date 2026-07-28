import pytest
from unittest.mock import MagicMock

import dropbox

from core.errors import AuthError


@pytest.fixture
def client(mocker):
    mocker.patch("clients.dropbox_client.DROPBOX_APP_KEY", "key")
    mocker.patch("clients.dropbox_client.DROPBOX_APP_SECRET", "secret")
    mocker.patch("clients.dropbox_client.DROPBOX_REFRESH_TOKEN", "refresh")
    mock_cls = mocker.patch("clients.dropbox_client.dropbox.Dropbox")
    from clients.dropbox_client import DropboxClient
    c = DropboxClient(folder="/lmu-setups")
    return c, mock_cls.return_value


def _entry(name, path_lower, path_display=None):
    e = MagicMock()
    e.name = name
    e.path_lower = path_lower
    e.path_display = path_display if path_display is not None else path_lower
    return e


def test_missing_credentials_raises(mocker):
    mocker.patch("clients.dropbox_client.DROPBOX_APP_KEY", None)
    mocker.patch("clients.dropbox_client.DROPBOX_APP_SECRET", "secret")
    mocker.patch("clients.dropbox_client.DROPBOX_REFRESH_TOKEN", "refresh")
    mocker.patch("clients.dropbox_client.dropbox.Dropbox")
    from clients.dropbox_client import DropboxClient
    with pytest.raises(RuntimeError):
        DropboxClient()


def test_list_setups_parses_and_filters(client):
    c, dbx = client
    res = MagicMock()
    res.entries = [
        # Dropbox nests these under a car subfolder, but entry.name is still
        # just the bare filename, same as a flat listing.
        _entry("HYMO-Spa_Porsche_uuid-1_1000.zip", "/lmu-setups/porsche/hymo-spa_porsche_uuid-1_1000.zip"),
        _entry("readme.txt", "/lmu-setups/readme.txt"),
        _entry("garbage.zip", "/lmu-setups/garbage.zip"),  # no id/ts -> skipped
        _entry("Spa_Porsche_uuid-2_1000.zip", "/lmu-setups/spa_porsche_uuid-2_1000.zip"),  # no HYMO- prefix -> skipped
    ]
    res.has_more = False
    dbx.files_list_folder.return_value = res

    setups = c.list_setups()

    assert len(setups) == 1
    assert setups[0].setup_id == "uuid-1"
    assert setups[0].ts == 1000
    dbx.files_list_folder.assert_called_once_with("/lmu-setups", recursive=True)


def test_list_setups_silently_skips_go_prefixed_zips(client, caplog):
    c, dbx = client
    res = MagicMock()
    res.entries = [
        _entry("GO-ORECA.zip", "/lmu-setups/oreca/imola/go-oreca.zip"),
        _entry("HYMO-Spa_Porsche_uuid-1_1000.zip", "/lmu-setups/porsche/spa/hymo-spa_porsche_uuid-1_1000.zip"),
    ]
    res.has_more = False
    dbx.files_list_folder.return_value = res

    with caplog.at_level("WARNING"):
        setups = c.list_setups()

    assert len(setups) == 1
    assert setups[0].setup_id == "uuid-1"
    assert "GO-ORECA.zip" not in caplog.text


def test_list_setups_paginates(client):
    c, dbx = client
    page1 = MagicMock()
    page1.entries = [_entry("HYMO-A_B_id1_1.zip", "/lmu-setups/car1/hymo-a_b_id1_1.zip")]
    page1.has_more = True
    page1.cursor = "c1"
    page2 = MagicMock()
    page2.entries = [_entry("HYMO-A_B_id2_2.zip", "/lmu-setups/car2/hymo-a_b_id2_2.zip")]
    page2.has_more = False
    dbx.files_list_folder.return_value = page1
    dbx.files_list_folder_continue.return_value = page2

    setups = c.list_setups()

    assert {s.setup_id for s in setups} == {"id1", "id2"}
    dbx.files_list_folder_continue.assert_called_once_with("c1")


@pytest.mark.parametrize("remote_name,expected_path", [
    ("Spa_P_id_5.zip", "/lmu-setups/Spa_P_id_5.zip"),
    ("Porsche_963/Spa_P_id_5.zip", "/lmu-setups/Porsche_963/Spa_P_id_5.zip"),
])
def test_upload_calls_sdk(client, tmp_path, remote_name, expected_path):
    c, dbx = client
    f = tmp_path / "pkg.zip"
    f.write_bytes(b"zipdata")

    remote = c.upload(f, remote_name)

    assert remote == expected_path
    args, _ = dbx.files_upload.call_args
    assert args[0] == b"zipdata"
    assert args[1] == expected_path


def test_download_to_calls_sdk(client, tmp_path):
    c, dbx = client
    local = tmp_path / "out" / "x.zip"

    result = c.download_to("/lmu-setups/x.zip", local)

    dbx.files_download_to_file.assert_called_once_with(str(local), "/lmu-setups/x.zip")
    assert result == local


def test_delete_calls_sdk(client):
    c, dbx = client
    c.delete("/lmu-setups/old.zip")
    dbx.files_delete_v2.assert_called_once_with("/lmu-setups/old.zip")


def _delete_not_found_error():
    delete_error = dropbox.files.DeleteError.path_lookup(dropbox.files.LookupError.not_found)
    return dropbox.exceptions.ApiError("req-id", delete_error, "msg", None)


def test_delete_if_exists_returns_true_on_success(client):
    c, dbx = client
    assert c.delete_if_exists("/lmu-setups/old.zip") is True
    dbx.files_delete_v2.assert_called_once_with("/lmu-setups/old.zip")


def test_delete_if_exists_returns_false_when_already_gone(client):
    c, dbx = client
    dbx.files_delete_v2.side_effect = _delete_not_found_error()
    assert c.delete_if_exists("/lmu-setups/gone.zip") is False


def test_delete_if_exists_reraises_other_api_errors(client):
    c, dbx = client
    delete_error = dropbox.files.DeleteError.too_many_write_operations
    dbx.files_delete_v2.side_effect = dropbox.exceptions.ApiError("req-id", delete_error, "msg", None)
    with pytest.raises(dropbox.exceptions.ApiError):
        c.delete_if_exists("/lmu-setups/busy.zip")


def test_list_setups_raises_auth_error_on_expired_token(client):
    c, dbx = client
    dbx.files_list_folder.side_effect = dropbox.exceptions.AuthError("req-id", "expired")
    with pytest.raises(AuthError) as exc_info:
        c.list_setups()
    assert exc_info.value.code == "dropbox"


def test_upload_raises_auth_error_on_expired_token(client, tmp_path):
    c, dbx = client
    f = tmp_path / "pkg.zip"
    f.write_bytes(b"zipdata")
    dbx.files_upload.side_effect = dropbox.exceptions.AuthError("req-id", "expired")
    with pytest.raises(AuthError):
        c.upload(f, "Spa_P_id_5.zip")


def test_download_raises_auth_error_on_stone_catch_all_bug(client, tmp_path):
    # Upstream dropbox/stone bug: some 401 responses carry {".tag": "other"},
    # which stone's own union decoder can't represent and raises
    # ValidationError instead of a clean dropbox.exceptions.AuthError. This is
    # still an auth failure from our point of view (most often a token whose
    # scope doesn't cover the call), so it must surface as our AuthError too.
    from stone.backends.python_rsrc.stone_validators import ValidationError as StoneValidationError

    c, dbx = client
    dbx.files_download_to_file.side_effect = StoneValidationError("unexpected use of the catch-all tag 'other'")
    with pytest.raises(AuthError) as exc_info:
        c.download_to("/lmu-setups/x.zip", tmp_path / "x.zip")
    assert exc_info.value.code == "dropbox_scope"


# ----- remote_path / move ---------------------------------------------------


def test_remote_path_builds_from_folder(client):
    c, dbx = client
    assert c.remote_path("Porsche_963/Spa/x.zip") == "/lmu-setups/Porsche_963/Spa/x.zip"


def test_move_calls_sdk(client):
    c, dbx = client
    c.move("/lmu-setups/old/x.zip", "/lmu-setups/new/x.zip")
    dbx.files_move_v2.assert_called_once_with("/lmu-setups/old/x.zip", "/lmu-setups/new/x.zip", autorename=False)


def test_move_raises_auth_error_on_expired_token(client):
    c, dbx = client
    dbx.files_move_v2.side_effect = dropbox.exceptions.AuthError("req-id", "expired")
    with pytest.raises(AuthError):
        c.move("/a.zip", "/b.zip")


# ----- list_go_setups ---------------------------------------------------------


def test_list_go_setups_parses_car_track_from_path_display(client):
    c, dbx = client
    res = MagicMock()
    res.entries = [
        _entry("GO-ORECA.zip", "/lmu-setups/oreca 07/imola/go-oreca.zip", "/lmu-setups/Oreca 07/Imola/GO-ORECA.zip"),
    ]
    res.has_more = False
    dbx.files_list_folder.return_value = res

    setups = c.list_go_setups()

    assert len(setups) == 1
    assert setups[0].car == "Oreca 07"
    assert setups[0].track == "Imola"
    assert setups[0].name == "GO-ORECA.zip"
    assert setups[0].path_lower == "/lmu-setups/oreca 07/imola/go-oreca.zip"


def test_list_go_setups_skips_and_warns_at_wrong_depth(client, caplog):
    c, dbx = client
    res = MagicMock()
    res.entries = [
        _entry("GO-Flat.zip", "/lmu-setups/go-flat.zip", "/lmu-setups/GO-Flat.zip"),
        _entry("GO-TooDeep.zip", "/lmu-setups/a/b/c/go-toodeep.zip", "/lmu-setups/A/B/C/GO-TooDeep.zip"),
    ]
    res.has_more = False
    dbx.files_list_folder.return_value = res

    with caplog.at_level("WARNING"):
        setups = c.list_go_setups()

    assert setups == []
    assert "GO-Flat.zip" in caplog.text
    assert "GO-TooDeep.zip" in caplog.text


def test_list_go_setups_silently_skips_non_go_entries_regardless_of_depth(client, caplog):
    c, dbx = client
    res = MagicMock()
    res.entries = [
        _entry("HYMO-Spa_Porsche_uuid-1_1000.zip", "/lmu-setups/porsche/hymo-spa.zip", "/lmu-setups/Porsche/HYMO-Spa_Porsche_uuid-1_1000.zip"),
        _entry("readme.txt", "/lmu-setups/readme.txt"),
    ]
    res.has_more = False
    dbx.files_list_folder.return_value = res

    with caplog.at_level("WARNING"):
        setups = c.list_go_setups()

    assert setups == []
    assert caplog.text == ""


def test_list_go_setups_ignores_non_zip(client):
    c, dbx = client
    res = MagicMock()
    res.entries = [
        _entry("GO-notes.txt", "/lmu-setups/oreca/imola/go-notes.txt", "/lmu-setups/Oreca/Imola/GO-notes.txt"),
    ]
    res.has_more = False
    dbx.files_list_folder.return_value = res

    assert c.list_go_setups() == []


def test_list_go_setups_paginates(client):
    c, dbx = client
    page1 = MagicMock()
    page1.entries = [_entry("GO-A.zip", "/lmu-setups/car1/track1/go-a.zip", "/lmu-setups/Car1/Track1/GO-A.zip")]
    page1.has_more = True
    page1.cursor = "c1"
    page2 = MagicMock()
    page2.entries = [_entry("GO-B.zip", "/lmu-setups/car2/track2/go-b.zip", "/lmu-setups/Car2/Track2/GO-B.zip")]
    page2.has_more = False
    dbx.files_list_folder.return_value = page1
    dbx.files_list_folder_continue.return_value = page2

    setups = c.list_go_setups()

    assert {s.car for s in setups} == {"Car1", "Car2"}
    dbx.files_list_folder_continue.assert_called_once_with("c1")


def test_list_go_setups_folder_not_found_returns_empty_list(client):
    c, dbx = client
    path_error = dropbox.files.ListFolderError.path(dropbox.files.LookupError.not_found)
    dbx.files_list_folder.side_effect = dropbox.exceptions.ApiError("req-id", path_error, "msg", None)
    assert c.list_go_setups() == []


def test_list_go_setups_raises_auth_error_on_expired_token(client):
    c, dbx = client
    dbx.files_list_folder.side_effect = dropbox.exceptions.AuthError("req-id", "expired")
    with pytest.raises(AuthError):
        c.list_go_setups()


# ----- delete_folder_if_empty / prune_empty_ancestor_folders -----------------


def test_delete_folder_if_empty_deletes_when_no_entries(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(entries=[])

    assert c.delete_folder_if_empty("/lmu-setups/Oreca 07/Imola") is True
    dbx.files_list_folder.assert_called_once_with("/lmu-setups/Oreca 07/Imola")
    dbx.files_delete_v2.assert_called_once_with("/lmu-setups/Oreca 07/Imola")


def test_delete_folder_if_empty_keeps_a_non_empty_folder(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(
        entries=[_entry("other.zip", "/lmu-setups/oreca 07/imola/other.zip")]
    )

    assert c.delete_folder_if_empty("/lmu-setups/Oreca 07/Imola") is False
    dbx.files_delete_v2.assert_not_called()


def test_delete_folder_if_empty_returns_false_when_folder_missing(client):
    c, dbx = client
    path_error = dropbox.files.ListFolderError.path(dropbox.files.LookupError.not_found)
    dbx.files_list_folder.side_effect = dropbox.exceptions.ApiError("req-id", path_error, "msg", None)

    assert c.delete_folder_if_empty("/lmu-setups/Gone/Track") is False
    dbx.files_delete_v2.assert_not_called()


def test_delete_folder_if_empty_reraises_other_api_errors(client):
    c, dbx = client
    dbx.files_list_folder.side_effect = dropbox.exceptions.ApiError(
        "req-id", dropbox.files.ListFolderError.other, "msg", None
    )

    with pytest.raises(dropbox.exceptions.ApiError):
        c.delete_folder_if_empty("/lmu-setups/Oreca 07/Imola")


def test_prune_empty_ancestor_folders_deletes_track_then_car(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(entries=[])

    c.prune_empty_ancestor_folders("/lmu-setups/Oreca 07/Imola/go-oreca.zip")

    dbx.files_list_folder.assert_any_call("/lmu-setups/Oreca 07/Imola")
    dbx.files_list_folder.assert_any_call("/lmu-setups/Oreca 07")
    dbx.files_delete_v2.assert_any_call("/lmu-setups/Oreca 07/Imola")
    dbx.files_delete_v2.assert_any_call("/lmu-setups/Oreca 07")


def test_prune_empty_ancestor_folders_never_deletes_the_share_root(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(entries=[])

    c.prune_empty_ancestor_folders("/lmu-setups/Oreca 07/x.zip")

    dbx.files_list_folder.assert_called_once_with("/lmu-setups/Oreca 07")
    dbx.files_delete_v2.assert_called_once_with("/lmu-setups/Oreca 07")


def test_prune_empty_ancestor_folders_stops_as_soon_as_a_folder_is_not_empty(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(
        entries=[_entry("sibling.zip", "/lmu-setups/oreca 07/spa/sibling.zip")]
    )

    c.prune_empty_ancestor_folders("/lmu-setups/Oreca 07/Imola/go-oreca.zip")

    # The Car folder still holds another Track's files - never even checked
    # once the Track folder itself turned out non-empty.
    dbx.files_list_folder.assert_called_once_with("/lmu-setups/Oreca 07/Imola")
    dbx.files_delete_v2.assert_not_called()


# ----- find_existing_setup ----------------------------------------------------


def test_find_existing_setup_returns_the_matching_hymo_zip(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(
        has_more=False,
        entries=[_entry("HYMO-Spa_Porsche_uuid-1_1000.zip", "/lmu-setups/porsche/spa/hymo-spa_porsche_uuid-1_1000.zip")],
    )

    found = c.find_existing_setup("Porsche", "Spa", "HYMO")

    assert found is not None
    assert found.setup_id == "uuid-1"
    assert found.ts == 1000
    dbx.files_list_folder.assert_called_once_with("/lmu-setups/Porsche/Spa")


def test_find_existing_setup_returns_the_matching_go_zip(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(
        has_more=False,
        entries=[_entry("GO-Spa_Porsche_uuid-1_1000.zip", "/lmu-setups/porsche/spa/go-spa_porsche_uuid-1_1000.zip")],
    )

    found = c.find_existing_setup("Porsche", "Spa", "GO")

    assert found is not None
    assert found.name == "GO-Spa_Porsche_uuid-1_1000.zip"


def test_find_existing_setup_ignores_the_other_types_zip(client):
    c, dbx = client
    dbx.files_list_folder.return_value = MagicMock(
        has_more=False,
        entries=[_entry("GO-Spa_Porsche_uuid-1_1000.zip", "/lmu-setups/porsche/spa/go-spa_porsche_uuid-1_1000.zip")],
    )

    assert c.find_existing_setup("Porsche", "Spa", "HYMO") is None


def test_find_existing_setup_returns_none_when_folder_missing(client):
    c, dbx = client
    path_error = dropbox.files.ListFolderError.path(dropbox.files.LookupError.not_found)
    dbx.files_list_folder.side_effect = dropbox.exceptions.ApiError("req-id", path_error, "msg", None)

    assert c.find_existing_setup("Porsche", "Spa", "HYMO") is None


def test_find_existing_setup_paginates(client):
    c, dbx = client
    page1 = MagicMock(has_more=True, cursor="c1", entries=[_entry("readme.txt", "/lmu-setups/porsche/spa/readme.txt")])
    page2 = MagicMock(
        has_more=False,
        entries=[_entry("HYMO-Spa_Porsche_uuid-1_1000.zip", "/lmu-setups/porsche/spa/hymo-spa_porsche_uuid-1_1000.zip")],
    )
    dbx.files_list_folder.return_value = page1
    dbx.files_list_folder_continue.return_value = page2

    found = c.find_existing_setup("Porsche", "Spa", "HYMO")

    assert found is not None
    assert found.setup_id == "uuid-1"
    dbx.files_list_folder_continue.assert_called_once_with("c1")


def test_find_existing_setup_raises_auth_error_on_expired_token(client):
    c, dbx = client
    dbx.files_list_folder.side_effect = dropbox.exceptions.AuthError("req-id", "expired")
    with pytest.raises(AuthError):
        c.find_existing_setup("Porsche", "Spa", "HYMO")


# ----- OAuth "no redirect" flow helpers -----------------------------------------

@pytest.mark.parametrize("scope", [None, "READ_ONLY_SCOPES"])
def test_get_authorization_url_starts_an_offline_flow(mocker, scope):
    # scope is looked up by name (rather than parametrized directly) so the
    # None case and the READ_ONLY_SCOPES case share one test body while still
    # covering both "no restriction" and "restricted below the app's scopes".
    from clients.dropbox_client import READ_ONLY_SCOPES
    scope = READ_ONLY_SCOPES if scope == "READ_ONLY_SCOPES" else None

    flow_cls = mocker.patch("clients.dropbox_client.dropbox.DropboxOAuth2FlowNoRedirect")
    flow_cls.return_value.start.return_value = "https://dropbox.com/oauth2/authorize?x=1"
    from clients.dropbox_client import get_authorization_url

    url = get_authorization_url("app-key", "app-secret", scope=scope)

    flow_cls.assert_called_once_with("app-key", "app-secret", token_access_type="offline", scope=scope)
    assert url == "https://dropbox.com/oauth2/authorize?x=1"


def test_read_write_scopes_cover_both_content_read_and_write():
    # Regression: READ_WRITE_SCOPES previously omitted files.content.read, so
    # the auto-generated "read/write" token could list and upload but any
    # download call (Slave, or Master's own relocate/move) failed auth.
    from clients.dropbox_client import READ_WRITE_SCOPES

    assert set(READ_WRITE_SCOPES) == {"files.metadata.read", "files.content.read", "files.content.write"}


def test_exchange_authorization_code_returns_the_refresh_token(mocker):
    flow_cls = mocker.patch("clients.dropbox_client.dropbox.DropboxOAuth2FlowNoRedirect")
    flow_cls.return_value.finish.return_value = MagicMock(refresh_token="the-refresh-token")
    from clients.dropbox_client import exchange_authorization_code

    token = exchange_authorization_code("app-key", "app-secret", " abc123 ")

    flow_cls.assert_called_once_with("app-key", "app-secret", token_access_type="offline")
    flow_cls.return_value.finish.assert_called_once_with("abc123")
    assert token == "the-refresh-token"
