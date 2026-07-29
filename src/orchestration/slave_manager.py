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
from domain.setup import RemoteSetup, Setup
from domain.setup_db import SetupDb
from domain.unmatched import UnmatchedTracker
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
        unmatched: Optional[UnmatchedTracker] = None,
    ) -> None:
        self.dropbox_client = dropbox_client
        self.setup_manager = setup_manager
        self.database = database
        self.on_progress = on_progress
        self.cancel_event = cancel_event
        self.unmatched = unmatched if unmatched is not None else UnmatchedTracker()

    def _emit(self, event: ProgressEvent) -> None:
        if self.on_progress is not None:
            self.on_progress(event)

    def run(self) -> None:
        for remote in self.dropbox_client.list_setups():
            if self.cancel_event is not None and self.cancel_event.is_set():
                self._emit(ProgressEvent(ProgressKind.STOPPED, "Install stopped", unmatched=self.unmatched.serialize()))
                return
            self._process(remote)
        for go_remote in self.dropbox_client.list_go_setups():
            if self.cancel_event is not None and self.cancel_event.is_set():
                self._emit(ProgressEvent(ProgressKind.STOPPED, "Install stopped", unmatched=self.unmatched.serialize()))
                return
            self._process_go(go_remote)
        self._emit(ProgressEvent(ProgressKind.FINISH, "Install completed", unmatched=self.unmatched.serialize()))

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

        # Unmatched car/track: ignored outright, never installed under a
        # placeholder "-HYMO" name - recorded for the end-of-run correction
        # dialog instead. Checked before START is even emitted, so a fully
        # ignored setup never appears in the activity log at all.
        car_matched = self.setup_manager.car_manager.get_car_name(setup.car) is not None
        track_matched = self.setup_manager.track_manager.get_track_folder_name(setup.track) is not None
        if not car_matched or not track_matched:
            log.warning(f"Setup not matched, skipping: {setup.track} - {setup.car}")
            self.unmatched.record(
                setup.track, setup.car, track_matched=track_matched, car_matched=car_matched,
            )
            if CLEAN_DOWNLOAD and local_zip.exists():
                local_zip.unlink()
            return

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
        # "<Track> - <Car> Setup" instead of the raw archive filename, and so
        # an unmatched pair can be skipped before ever downloading it (the
        # GO folder layout carries car/track without needing the zip's
        # content, unlike a HYMO archive's embedded metadata).
        car = self.setup_manager.car_manager.get_car_name(remote.car)
        track = self.setup_manager.track_manager.get_official_track_name(remote.track)
        if car is None or track is None:
            log.warning(f"GO Setup not matched, skipping: {remote.track} - {remote.car}")
            self.unmatched.record(
                remote.track, remote.car, track_matched=track is not None, car_matched=car is not None,
            )
            return
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
            extensions=GO_SETUP_FILE_EXTENSIONS, setup_type="GO",
            sha256=sha256,
        )
        self._emit(ProgressEvent(ProgressKind.INSTALL, label))
