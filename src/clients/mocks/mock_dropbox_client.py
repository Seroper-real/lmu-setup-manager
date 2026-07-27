import logging
import shutil
from pathlib import Path
from typing import Optional

from core.config import SANDBOX_DROPBOX_PATH
from domain.go_setup import RemoteGoSetup, is_go_zip_name, looks_like_go_name, parse_go_entry
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
            if is_go_zip_name(entry.name):
                # GO Setups archives are a recognized, expected coexisting file
                # type now (see list_go_setups()), not stray files.
                continue
            parsed = parse_remote_zip_name(entry.name)
            if parsed is None:
                log.warning(f"Ignoring non-conforming file on share: {entry.name}")
                continue
            setup_id, ts = parsed
            result.append(
                RemoteSetup(name=entry.name, path_lower=str(entry.resolve()), setup_id=setup_id, ts=ts)
            )
        return result

    def list_go_setups(self) -> list[RemoteGoSetup]:
        result: list[RemoteGoSetup] = []
        for entry in sorted(self.folder.glob("**/*.zip")):
            if not looks_like_go_name(entry.name):
                continue
            segments = list(entry.relative_to(self.folder).parts)
            parsed = parse_go_entry(entry.name, str(entry.resolve()), segments)
            if parsed is None:
                log.warning(f"Ignoring non-conforming GO Setup entry on share: {entry}")
                continue
            result.append(parsed)
        return result

    def download_to(self, path_lower: str, local_path: str | Path) -> Path:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path_lower, local_path)
        log.info(f"SANDBOX: copied from mock share: {path_lower} -> {local_path}")
        return local_path

    def upload(self, local_path: str | Path, remote_name: str) -> str:
        remote_path = self.remote_path(remote_name)
        Path(remote_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, remote_path)
        log.info(f"SANDBOX: copied to mock share: {remote_path}")
        return remote_path

    def remote_path(self, relative_path: str) -> str:
        return str((self.folder / relative_path).resolve())

    def move(self, from_path: str, to_path: str) -> None:
        dst = Path(to_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(Path(from_path)), str(dst))
        log.info(f"SANDBOX: moved on mock share: {from_path} -> {to_path}")

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

    def delete_folder_if_empty(self, path: str) -> bool:
        folder = Path(path)
        if not folder.is_dir() or any(folder.iterdir()):
            return False
        folder.rmdir()
        log.info(f"SANDBOX: deleted empty folder from mock share: {path}")
        return True

    def prune_empty_ancestor_folders(self, path: str, levels: int = 2) -> None:
        root = self.folder.resolve()
        current = Path(path).parent
        for _ in range(levels):
            if current.resolve() == root:
                return
            if not self.delete_folder_if_empty(str(current)):
                return
            current = current.parent
