import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.config import SANDBOX_TRACKTITAN_PATH

log = logging.getLogger("TrackTitanDownloader")

# Scheme used by the mock download links. Carries the setup id back to download().
_URL_SCHEME = "sandbox://"

CATALOG_FILENAME = "catalog.json"
SETUPS_DIRNAME = "setups"


@dataclass
class MockResponse:
    """Stands in for requests.Response. DownloadManager only reads .content."""
    content: bytes


class MockTrackTitanClient:
    """Serves a checked-in fixture catalog instead of calling the TrackTitan API.

    Requires no tokens. Paginates the catalog exactly like the real endpoint so
    DownloadManager's page/limit loop and its short-page termination are exercised.
    """

    def __init__(self, base_path: Optional[Path] = None) -> None:
        # Resolved at call time (not as a default argument) so the fixture root
        # stays redirectable.
        self.base_path: Path = Path(base_path) if base_path is not None else SANDBOX_TRACKTITAN_PATH
        self.catalog_path: Path = self.base_path / CATALOG_FILENAME
        self.setups_path: Path = self.base_path / SETUPS_DIRNAME
        if not self.catalog_path.exists():
            raise RuntimeError(f"Sandbox catalog not found: {self.catalog_path}")

    def _load_setups(self) -> list[dict[str, Any]]:
        with self.catalog_path.open(encoding="utf-8") as f:
            catalog: dict[str, Any] = json.load(f)
        return catalog["data"]["setups"]

    def known_setup_ids(self) -> set[str]:
        """Every setup id in the fixture catalog. Used by the sandbox cleanup
        utility to recognize which remote Dropbox entries are test data safe to
        delete, without needing to page through get()/download_link()."""
        return {setup["id"] for setup in self._load_setups()}

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        params = params or {}
        page: int = int(params.get("page", 1))
        limit: int = int(params.get("limit", 12))

        setups: list[dict[str, Any]] = self._load_setups()
        start: int = (page - 1) * limit
        window: list[dict[str, Any]] = setups[start:start + limit]

        log.debug(f"SANDBOX: serving {len(window)} setup(s) for page {page} of {path}")
        return {"data": {"setups": window}}

    def download_link(self, setup_id: str) -> dict[str, Any]:
        return {"url": f"{_URL_SCHEME}{setup_id}"}

    def download(self, url: str) -> MockResponse:
        if not url.startswith(_URL_SCHEME):
            raise ValueError(f"Not a sandbox download url: {url}")
        setup_id = url[len(_URL_SCHEME):]

        zip_path = self.setups_path / f"{setup_id}.zip"
        if not zip_path.exists():
            raise FileNotFoundError(f"Sandbox setup archive not found: {zip_path}")

        return MockResponse(content=zip_path.read_bytes())

    def throttle(self) -> None:
        # No bot detection to evade against a local fixture: keep sandbox runs instant.
        return None
