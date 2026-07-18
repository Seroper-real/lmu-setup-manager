import json
import logging
import threading
from pathlib import Path
from typing import Optional

from core.archive import METADATA_FILENAME, read_zip_member
from clients.protocols import DropboxClientProtocol
from core.config import DOWNLOAD_PATH
from core.progress import ProgressCallback, ProgressEvent, ProgressKind
from domain.setup import RemoteSetup, Setup
from domain.setup_db import SetupDb
from processing.setup_manager import SetupManager

log = logging.getLogger("TrackTitanDownloader")


class SlaveManager:
    """Installs setups published to a Dropbox share. Uses the DB so it stays
    compatible with FULL mode on the same machine; rebuilds DB records from the
    .metadata.json embedded in each package."""

    def __init__(
        self,
        dropbox_client: DropboxClientProtocol,
        setup_manager: SetupManager,
        database: SetupDb,
        *,
        on_progress: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        self.dropbox_client = dropbox_client
        self.setup_manager = setup_manager
        self.database = database
        self.on_progress = on_progress
        self.cancel_event = cancel_event

    def _emit(self, event: ProgressEvent) -> None:
        if self.on_progress is not None:
            self.on_progress(event)

    def run(self) -> None:
        # FULL-compat housekeeping: relocate setups whose track mapping changed.
        self.setup_manager.update_tracks_not_found()
        for remote in self.dropbox_client.list_setups():
            if self.cancel_event is not None and self.cancel_event.is_set():
                self._emit(ProgressEvent(ProgressKind.STOPPED, "Install stopped"))
                return
            self._process(remote)
        self._emit(ProgressEvent(ProgressKind.FINISH, "Install completed"))

    def _process(self, remote: RemoteSetup) -> None:
        log.info("#################")
        log.info(f"  ID: {remote.setup_id}")
        log.info(f"  File: {remote.name}")
        self._emit(ProgressEvent(ProgressKind.START, remote.name))

        if self.database.is_installed_last_version(remote.setup_id, remote.ts):
            log.info("Already installed (latest version). Skipping.")
            return

        local_zip = Path(DOWNLOAD_PATH) / remote.name
        self.dropbox_client.download_to(remote.path_lower, local_zip)

        try:
            metadata = json.loads(read_zip_member(local_zip, METADATA_FILENAME))
        except (KeyError, json.JSONDecodeError) as e:
            log.error(f"Missing/invalid {METADATA_FILENAME} in {remote.name}: {e}. Skipping.")
            return

        setup = Setup(metadata)
        # install_setup re-unzips, copies .svm into the LMU track folder, and
        # records the setup in the DB. The .metadata.json member is ignored by
        # the .svm-only file filter.
        self.setup_manager.install_setup(local_zip, setup)
        self._emit(ProgressEvent(ProgressKind.INSTALL, remote.name))
