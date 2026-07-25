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


def test_upload_calls_sdk(client, tmp_path):
    c, dbx = client
    f = tmp_path / "pkg.zip"
    f.write_bytes(b"zipdata")

    remote = c.upload(f, "Spa_P_id_5.zip")

    assert remote == "/lmu-setups/Spa_P_id_5.zip"
    args, _ = dbx.files_upload.call_args
    assert args[0] == b"zipdata"
    assert args[1] == "/lmu-setups/Spa_P_id_5.zip"


def test_upload_calls_sdk_with_nested_name(client, tmp_path):
    c, dbx = client
    f = tmp_path / "pkg.zip"
    f.write_bytes(b"zipdata")

    remote = c.upload(f, "Porsche_963/Spa_P_id_5.zip")

    assert remote == "/lmu-setups/Porsche_963/Spa_P_id_5.zip"
    args, _ = dbx.files_upload.call_args
    assert args[1] == "/lmu-setups/Porsche_963/Spa_P_id_5.zip"


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


def test_upload_uses_remote_path(client, tmp_path):
    c, dbx = client
    f = tmp_path / "pkg.zip"
    f.write_bytes(b"data")
    remote = c.upload(f, "Porsche_963/Spa/x.zip")
    assert remote == c.remote_path("Porsche_963/Spa/x.zip")


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


# ----- OAuth "no redirect" flow helpers -----------------------------------------

def test_get_authorization_url_starts_an_offline_flow(mocker):
    flow_cls = mocker.patch("clients.dropbox_client.dropbox.DropboxOAuth2FlowNoRedirect")
    flow_cls.return_value.start.return_value = "https://dropbox.com/oauth2/authorize?x=1"
    from clients.dropbox_client import get_authorization_url

    url = get_authorization_url("app-key", "app-secret")

    flow_cls.assert_called_once_with("app-key", "app-secret", token_access_type="offline", scope=None)
    assert url == "https://dropbox.com/oauth2/authorize?x=1"


def test_read_write_scopes_cover_both_content_read_and_write():
    # Regression: READ_WRITE_SCOPES previously omitted files.content.read, so
    # the auto-generated "read/write" token could list and upload but any
    # download call (Slave, or Master's own relocate/move) failed auth.
    from clients.dropbox_client import READ_WRITE_SCOPES

    assert set(READ_WRITE_SCOPES) == {"files.metadata.read", "files.content.read", "files.content.write"}


def test_get_authorization_url_forwards_the_requested_scope(mocker):
    flow_cls = mocker.patch("clients.dropbox_client.dropbox.DropboxOAuth2FlowNoRedirect")
    flow_cls.return_value.start.return_value = "https://dropbox.com/oauth2/authorize?x=1"
    from clients.dropbox_client import get_authorization_url, READ_ONLY_SCOPES

    get_authorization_url("app-key", "app-secret", scope=READ_ONLY_SCOPES)

    flow_cls.assert_called_once_with("app-key", "app-secret", token_access_type="offline", scope=READ_ONLY_SCOPES)


def test_exchange_authorization_code_returns_the_refresh_token(mocker):
    flow_cls = mocker.patch("clients.dropbox_client.dropbox.DropboxOAuth2FlowNoRedirect")
    flow_cls.return_value.finish.return_value = MagicMock(refresh_token="the-refresh-token")
    from clients.dropbox_client import exchange_authorization_code

    token = exchange_authorization_code("app-key", "app-secret", " abc123 ")

    flow_cls.assert_called_once_with("app-key", "app-secret", token_access_type="offline")
    flow_cls.return_value.finish.assert_called_once_with("abc123")
    assert token == "the-refresh-token"
