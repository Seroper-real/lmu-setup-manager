import logging
from pathlib import Path
from typing import Callable, TypeVar

import dropbox
from stone.backends.python_rsrc.stone_validators import ValidationError as StoneValidationError

from core.config import (
    DROPBOX_APP_KEY,
    DROPBOX_APP_SECRET,
    DROPBOX_REFRESH_TOKEN,
    DROPBOX_FOLDER,
    DROPBOX_TIMEOUT,
)
from core.errors import AuthError
from domain.go_setup import RemoteGoSetup, is_go_zip_name, looks_like_go_name, parse_go_entry
# Re-exported so existing `from dropbox_client import RemoteSetup` keeps working.
from domain.setup import RemoteSetup, parse_remote_zip_name

T = TypeVar("T")

log = logging.getLogger("TrackTitanDownloader")

__all__ = [
    "DropboxClient",
    "RemoteSetup",
    "get_authorization_url",
    "exchange_authorization_code",
    "READ_WRITE_SCOPES",
    "READ_ONLY_SCOPES",
]

# Scopes for each token type offered by the Settings "get automatically" dialog.
# READ_WRITE_SCOPES must cover every call either mode makes on DropboxClient -
# Master (Upload only) lists+uploads+deletes, Slave (Install only) lists+
# downloads - so it works as a single do-everything token (e.g. FULL mode, or
# one machine running both roles), same as the full-scope token from the
# manual procedure in the README. It must include files.content.read even
# though Master itself never downloads: without it, the token can list and
# upload but any download call fails auth, which is easy to miss until Slave
# (or a relocate/move) is actually exercised with it.
READ_WRITE_SCOPES = ["files.metadata.read", "files.content.read", "files.content.write"]
READ_ONLY_SCOPES = ["files.metadata.read", "files.content.read"]


def get_authorization_url(app_key: str, app_secret: str, scope: list[str] | None = None) -> str:
    """Starts the OAuth2 "no redirect" flow (the CLI/desktop-app variant with no
    web server to receive a redirect) and returns the URL the user must open to
    approve the app. token_access_type="offline" is what makes Dropbox hand back
    a refresh token - not just a short-lived access token - once the resulting
    auth code is exchanged via exchange_authorization_code(). Passing scope (e.g.
    READ_ONLY_SCOPES) restricts the resulting token below whatever the Dropbox
    app itself is configured to allow, so a single app can hand out both
    read-only and read-write tokens."""
    flow = dropbox.DropboxOAuth2FlowNoRedirect(app_key, app_secret, token_access_type="offline", scope=scope)
    return flow.start()


def exchange_authorization_code(app_key: str, app_secret: str, auth_code: str) -> str:
    """Exchanges the authorization code the user pasted back for a long-lived
    refresh token. A fresh flow instance is fine here (no CSRF/session state to
    carry over): the no-redirect flow only needs the same app key/secret used
    to start it."""
    flow = dropbox.DropboxOAuth2FlowNoRedirect(app_key, app_secret, token_access_type="offline")
    result = flow.finish(auth_code.strip())
    return result.refresh_token


class DropboxClient:
    """Thin wrapper over the Dropbox SDK using refresh-token (auto-renew) auth.

    Read-only vs read-write is enforced by the Dropbox app's granted scopes, not
    by this client: SLAVE deployments simply ship read-only credentials.
    """

    def __init__(self, folder: str = DROPBOX_FOLDER) -> None:
        if not all([DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN]):
            raise RuntimeError(
                "Missing Dropbox credentials (DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN)"
            )
        # Normalize: Dropbox paths are "/folder" (root is "").
        self.folder: str = "/" + folder.strip("/") if folder.strip("/") else ""
        self.dbx = dropbox.Dropbox(
            oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
            app_key=DROPBOX_APP_KEY,
            app_secret=DROPBOX_APP_SECRET,
            timeout=DROPBOX_TIMEOUT,
        )

    def list_setups(self) -> list[RemoteSetup]:
        """List the share folder, returning only conforming setup zips."""
        result: list[RemoteSetup] = []
        for entry in self._list_all_entries():
            name = getattr(entry, "name", None)
            path_lower = getattr(entry, "path_lower", None)
            if not name or not path_lower or not name.lower().endswith(".zip"):
                continue
            if is_go_zip_name(name):
                # GO Setups archives are a recognized, expected coexisting file
                # type now (see list_go_setups()), not stray files.
                continue
            parsed = parse_remote_zip_name(name)
            if parsed is None:
                log.warning(f"Ignoring non-conforming file on share: {name}")
                continue
            setup_id, ts = parsed
            result.append(RemoteSetup(name=name, path_lower=path_lower, setup_id=setup_id, ts=ts))
        return result

    def list_go_setups(self) -> list[RemoteGoSetup]:
        """List the share folder, returning only conforming GO Setups archives -
        zips found exactly 3 segments deep (<Car>/<Track>/<file.zip>) whose name
        starts with "GO"."""
        result: list[RemoteGoSetup] = []
        folder_depth = len([s for s in self.folder.split("/") if s])
        for entry in self._list_all_entries():
            name = getattr(entry, "name", None)
            if not name or not looks_like_go_name(name):
                continue
            path_lower = getattr(entry, "path_lower", None)
            # path_display (not path_lower) is used to derive car/track, since
            # Dropbox's SDK always lowercases path_lower and the car name must
            # be preserved verbatim.
            path_display = getattr(entry, "path_display", None)
            if not path_lower or not path_display:
                continue
            segments = [s for s in path_display.split("/") if s][folder_depth:]
            parsed = parse_go_entry(name, path_lower, segments)
            if parsed is None:
                log.warning(f"Ignoring non-conforming GO Setup entry on share: {path_display}")
                continue
            result.append(parsed)
        return result

    def _list_all_entries(self) -> list:
        try:
            res = self._call(self.dbx.files_list_folder, self.folder, recursive=True)
        except dropbox.exceptions.ApiError as e:
            if self._is_not_found(e):
                log.warning(f"Dropbox folder not found, treating as empty: {self.folder}")
                return []
            raise
        entries = list(res.entries)
        while res.has_more:
            res = self._call(self.dbx.files_list_folder_continue, res.cursor)
            entries.extend(res.entries)
        return entries

    @staticmethod
    def _is_not_found(error: dropbox.exceptions.ApiError) -> bool:
        try:
            err = error.error
            return err.is_path() and err.get_path().is_not_found()
        except Exception:
            return False

    @staticmethod
    def _call(fn: Callable[..., T], *args, **kwargs) -> T:
        """Run a Dropbox SDK call, translating an expired/invalid token into our
        own AuthError so the GUI can show a dedicated "reconnect Dropbox" popup
        instead of a generic run-failed message."""
        try:
            return fn(*args, **kwargs)
        except dropbox.exceptions.AuthError as e:
            raise AuthError(
                "Dropbox authentication failed. Your credentials may have expired "
                "or been revoked - update them in Settings.",
                code="dropbox",
            ) from e
        except StoneValidationError as e:
            # Upstream SDK bug: on a 401 whose body is {".tag": "other"} (Dropbox's
            # own escape hatch for an auth failure it won't name more precisely -
            # most often a token whose granted scope doesn't cover this call, e.g.
            # metadata-only when content read/write is required), stone's decoder
            # can't represent its own catch-all tag and raises ValidationError
            # instead of a clean dropbox.exceptions.AuthError. Still an auth
            # failure from our point of view, so surface it the same way.
            raise AuthError(
                "Dropbox authentication failed (malformed error response for a 401 "
                "- usually a token whose scope doesn't cover this operation). "
                "Update your credentials in Settings, making sure the token "
                "includes content read/write access, not just metadata access.",
                code="dropbox_scope",
            ) from e

    def download_to(self, path_lower: str, local_path: str | Path) -> Path:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._call(self.dbx.files_download_to_file, str(local_path), path_lower)
        log.info(f"Downloaded from Dropbox: {path_lower} -> {local_path}")
        return local_path

    def upload(self, local_path: str | Path, remote_name: str) -> str:
        local_path = Path(local_path)
        remote_path = self.remote_path(remote_name)
        with open(local_path, "rb") as f:
            data = f.read()
        self._call(self.dbx.files_upload, data, remote_path, mode=dropbox.files.WriteMode("overwrite"))
        log.info(f"Uploaded to Dropbox: {remote_path}")
        return remote_path

    def remote_path(self, relative_path: str) -> str:
        return f"{self.folder}/{relative_path}"

    def move(self, from_path: str, to_path: str) -> None:
        self._call(self.dbx.files_move_v2, from_path, to_path, autorename=False)
        log.info(f"Moved on Dropbox: {from_path} -> {to_path}")

    def delete(self, path: str) -> None:
        self._call(self.dbx.files_delete_v2, path)
        log.info(f"Deleted from Dropbox: {path}")

    def delete_if_exists(self, path: str) -> bool:
        """Same as delete(), but a path already missing on Dropbox is treated as
        a no-op (returns False) instead of raising - used by the sandbox cleanup
        utility, where one already-deleted test file must not abort the rest."""
        try:
            self._call(self.dbx.files_delete_v2, path)
        except dropbox.exceptions.ApiError as e:
            if self._is_delete_not_found(e):
                log.warning(f"Already deleted from Dropbox, skipping: {path}")
                return False
            raise
        log.info(f"Deleted from Dropbox: {path}")
        return True

    @staticmethod
    def _is_delete_not_found(error: dropbox.exceptions.ApiError) -> bool:
        try:
            err = error.error
            return err.is_path_lookup() and err.get_path_lookup().is_not_found()
        except Exception:
            return False

    def delete_folder_if_empty(self, path: str) -> bool:
        """Delete a share folder, but only if it currently holds nothing.
        Dropbox folders are real, persistent objects - unlike a path prefix on
        S3, they do not disappear on their own once the last file inside is
        deleted, so a bulk setup-delete leaves the <Car>/<Track> tree behind
        unless this is called too."""
        try:
            res = self._call(self.dbx.files_list_folder, path)
        except dropbox.exceptions.ApiError as e:
            if self._is_not_found(e):
                return False
            raise
        if res.entries:
            return False
        return self.delete_if_exists(path)

    def prune_empty_ancestor_folders(self, path: str, levels: int = 2) -> None:
        """Walk up from a just-deleted file's path (Track, then its parent
        Car) deleting each ancestor folder while it's empty, stopping as soon
        as one still holds something (its parent can't be empty either) or the
        share root itself is reached. path_lower is always "/"-separated by
        Dropbox regardless of host OS, so plain string splitting is safe here."""
        current = path
        for _ in range(levels):
            current = current.rsplit("/", 1)[0]
            if not current or current == self.folder:
                return
            if not self.delete_folder_if_empty(current):
                return
