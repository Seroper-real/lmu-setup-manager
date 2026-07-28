import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from core.archive import METADATA_FILENAME, read_zip_member, sha256_file
from clients.protocols import DropboxClientProtocol
from core.config import CLEAN_DOWNLOAD, DOWNLOAD_PATH, GO_SETUP_FILE_EXTENSIONS
from core.progress import ProgressCallback, ProgressEvent, ProgressKind
from domain.go_setup import RemoteGoSetup
from domain.setup import RemoteSetup, Setup, sanitize_identity
from domain.setup_db import SetupDb
from processing.setup_manager import SetupManager

log = logging.getLogger("TrackTitanDownloader")


class SlaveManager:
    """Installs setups published to a Dropbox share: this tool's own TrackTitan
    setups plus manually-uploaded GO Setups archives. Uses the DB so it stays
    compatible with FULL mode on the same machine; rebuilds DB records from the
    .metadata.json embedded in each package (or, for GO, from the Dropbox
    car/track folder structure)."""

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
        for go_remote in self.dropbox_client.list_go_setups():
            if self.cancel_event is not None and self.cancel_event.is_set():
                self._emit(ProgressEvent(ProgressKind.STOPPED, "Install stopped"))
                return
            self._process_go(go_remote)
        self._emit(ProgressEvent(ProgressKind.FINISH, "Install completed"))

    def _process(self, remote: RemoteSetup) -> None:
        log.info("#################")
        log.info(f"  ID: {remote.setup_id}")
        log.info(f"  File: {remote.name}")

        if self.database.is_installed_last_version(remote.setup_id, remote.ts):
            log.info("Already installed (latest version). Skipping.")
            return

        local_zip = Path(DOWNLOAD_PATH) / remote.name
        self.dropbox_client.download_to(remote.path_lower, local_zip)
        sha256 = sha256_file(local_zip)

        try:
            metadata = json.loads(read_zip_member(local_zip, METADATA_FILENAME))
        except (KeyError, json.JSONDecodeError) as e:
            log.error(f"Missing/invalid {METADATA_FILENAME} in {remote.name}: {e}. Skipping.")
            return

        setup = Setup(metadata)
        # "<Track> - <Car> Setup" reads far better in the activity log than the
        # archive filename (e.g. Spa_Porsche_963_id1_1000.zip) it replaces.
        label = f"{setup.track} - {setup.car} Setup"
        self._emit(ProgressEvent(ProgressKind.START, label))
        # install_setup re-unzips, copies .svm into the LMU track folder, and
        # records the setup in the DB. The .metadata.json member is ignored by
        # the .svm-only file filter.
        self.setup_manager.install_setup(local_zip, setup, sha256=sha256)
        self._emit(ProgressEvent(ProgressKind.INSTALL, label))

    def _process_go(self, remote: RemoteGoSetup) -> None:
        # installed_setups.car/.track now hold the officialized catalog name
        # (see CarManager/TrackManager), not the raw Dropbox folder segments -
        # resolve remote.car/remote.track the same way install_setup() will
        # below, so these two lookups agree with what a HYMO row actually has
        # stored even when the raw folder text differs from the official name
        # but still matches its `matcher` regex. Resolved up front (rather than
        # after the download, as before) so the activity log can show
        # "<Track> - <Car> Setup" instead of the raw archive filename.
        car = self.setup_manager.car_manager.get_car_name(remote.car) or sanitize_identity(remote.car)
        track = self.setup_manager.track_manager.get_official_track_name(remote.track) or sanitize_identity(remote.track)
        label = f"{track} - {car} Setup"

        log.info("#################")
        log.info(f"  GO Setup: {remote.car} - {remote.track}")
        log.info(f"  File: {remote.name}")
        self._emit(ProgressEvent(ProgressKind.START, label))

        local_zip = Path(DOWNLOAD_PATH) / "go" / remote.car / remote.track / remote.name
        self.dropbox_client.download_to(remote.path_lower, local_zip)
        sha256 = sha256_file(local_zip)

        # Identity is the <Car>/<Track> pair alone, never the filename: the
        # archive can be renamed or have its content replaced in place by hand,
        # so only the checksum comparison below decides "already installed".
        existing = self.database.fetch_installed_go_setup(car, track)
        if existing and existing.sha256 == sha256:
            log.info("GO Setup unchanged since last install. Skipping.")
            if CLEAN_DOWNLOAD and local_zip.exists():
                local_zip.unlink()
            return

        setup_id = existing.setup_id if existing else str(uuid.uuid4())
        setup = Setup({
            "id": setup_id,
            "title": f"{remote.car} - {remote.track} (GO)",
            "setupCombos": [{"car": {"name": remote.car}, "track": {"name": remote.track}}],
            "hotlapLink": None,
            "lastUpdatedAt": int(time.time() * 1000),
            "isBundle": False,
        })
        self.setup_manager.install_setup(
            local_zip, setup,
            extensions=GO_SETUP_FILE_EXTENSIONS, setup_type="GO", fallback_suffix="GO",
            sha256=sha256,
        )
        self._emit(ProgressEvent(ProgressKind.INSTALL, label))
