import logging
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

from core.config import MOCK_DROPBOX, MOCK_TRACKTITAN
from domain.setup import RemoteSetup

log = logging.getLogger("TrackTitanDownloader")


@runtime_checkable
class SupportsContent(Protocol):
    """The only part of requests.Response that DownloadManager touches."""

    @property
    def content(self) -> bytes: ...


@runtime_checkable
class TrackTitanClientProtocol(Protocol):
    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]: ...

    def download_link(self, setup_id: str) -> dict[str, Any]: ...

    def download(self, url: str) -> SupportsContent: ...

    def throttle(self) -> None: ...


@runtime_checkable
class DropboxClientProtocol(Protocol):
    def list_setups(self) -> list[RemoteSetup]: ...

    def download_to(self, path_lower: str, local_path: str | Path) -> Path: ...

    def upload(self, local_path: str | Path, remote_name: str) -> str: ...

    def delete(self, path: str) -> None: ...

    def delete_if_exists(self, path: str) -> bool: ...


def build_track_titan_client() -> TrackTitanClientProtocol:
    """Return the mock or the real TrackTitan client per the sandbox flags.

    Imports are local so a sandbox run never constructs the real, token-validating
    client (and vice versa).
    """
    if MOCK_TRACKTITAN:
        from clients.mocks.mock_track_titan_client import MockTrackTitanClient

        log.warning("SANDBOX: using mock TrackTitan client (no API calls, no tokens)")
        return MockTrackTitanClient()

    from clients.track_titan_client import TrackTitanClient

    return TrackTitanClient()


def build_dropbox_client() -> DropboxClientProtocol:
    """Return the mock or the real Dropbox client per the sandbox flags."""
    if MOCK_DROPBOX:
        from clients.mocks.mock_dropbox_client import MockDropboxClient

        log.warning("SANDBOX: using mock Dropbox client (local folder, no credentials)")
        return MockDropboxClient()

    from clients.dropbox_client import DropboxClient

    return DropboxClient()
