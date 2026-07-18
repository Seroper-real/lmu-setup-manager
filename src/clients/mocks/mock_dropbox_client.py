import logging
import shutil
from pathlib import Path
from typing import Optional

from core.config import SANDBOX_DROPBOX_PATH
from domain.setup import RemoteSetup, parse_remote_zip_name

log = logging.getLogger("TrackTitanDownloader")


class MockDropboxClient:
    """A local directory standing in for the Dropbox share.

    Mirrors DropboxClient's surface (list_setups/download_to/upload/delete) so a
    MASTER run followed by a SLAVE run completes a publish -> install round trip
    with no credentials. `path_lower` carries an absolute local path here, which
    is all the managers ever do with it: hand it back to download_to/delete.
    """

    def __init__(self, folder: Optional[Path] = None) -> None:
        # Resolved at call time (not as a default argument) so the share root
        # stays redirectable.
        self.folder: Path = Path(folder) if folder is not None else SANDBOX_DROPBOX_PATH
        self.folder.mkdir(parents=True, exist_ok=True)

    def list_setups(self) -> list[RemoteSetup]:
        result: list[RemoteSetup] = []
        for entry in sorted(self.folder.glob("**/*.zip")):
            parsed = parse_remote_zip_name(entry.name)
            if parsed is None:
                log.warning(f"Ignoring non-conforming file on share: {entry.name}")
                continue
            setup_id, ts = parsed
            result.append(
                RemoteSetup(name=entry.name, path_lower=str(entry.resolve()), setup_id=setup_id, ts=ts)
            )
        return result

    def download_to(self, path_lower: str, local_path: str | Path) -> Path:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path_lower, local_path)
        log.info(f"SANDBOX: copied from mock share: {path_lower} -> {local_path}")
        return local_path

    def upload(self, local_path: str | Path, remote_name: str) -> str:
        remote_path = self.folder / remote_name
        remote_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, remote_path)
        log.info(f"SANDBOX: copied to mock share: {remote_path}")
        return str(remote_path)

    def delete(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)
        log.info(f"SANDBOX: deleted from mock share: {path}")

    def delete_if_exists(self, path: str) -> bool:
        existed = Path(path).exists()
        Path(path).unlink(missing_ok=True)
        if existed:
            log.info(f"SANDBOX: deleted from mock share: {path}")
        else:
            log.warning(f"SANDBOX: already deleted from mock share, skipping: {path}")
        return existed
