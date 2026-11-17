import logging
import shutil
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Optional

from clients.protocols import DropboxClientProtocol
from core.archive import sha256_file
from core.config import CLEAN_DOWNLOAD, DOWNLOAD_PATH
from core.errors import AuthError
from core.progress import ProgressCallback, ProgressEvent, ProgressKind
from domain.setup import RemoteSetup, Setup
from domain.setup_db import SetupDb
from domain.unmatched import UnmatchedTracker
from orchestration.download_manager import DownloadManager
from orchestration.master_manager import DropboxClientFactory, MasterManager
from processing.car_manager import CarManager
from processing.setup_manager import SetupManager
from processing.track_manager import TrackManager

log = logging.getLogger("TrackTitanDownloader")


class DualManager(MasterManager):
    """DUAL ("Upload + Locale"): MASTER's publish flow, plus a local install of
    every package it handles, recorded in the DB exactly like FULL/SLAVE.

    The two halves are decided independently: the share listing drives the
    upload (inherited from MasterManager), SetupDb.is_installed_last_version
    drives the local install. All the local-install work runs on the producer
    (main orchestration) thread, never on the publish pool:

    - the sqlite connection is bound to the thread that opened it, and
      SetupManager.install_setup is not safe to run concurrently with itself;
    - install_setup extracts into DOWNLOAD_PATH/<setup id>, the same folder
      MasterManager._publish extracts into - installing before the package is
      submitted to the pool means the two never overlap for the same id;
    - install_setup consumes (and, with CLEAN_DOWNLOAD, deletes) the archive it
      is given, so it is handed a staged copy, never the original the publish
      worker still needs.

    Install time spent on the producer thread overlaps the TrackTitan throttle
    interval (TrackTitanClient.throttle() counts caller work toward it), so it
    adds little or nothing to the run.

    A failure in either half never aborts the other or the run: install errors
    are logged and counted here, upload errors keep flowing through the
    inherited _report.
    """

    def __init__(
        self,
        download_manager: DownloadManager,
        dropbox_client: DropboxClientProtocol,
        setup_manager: SetupManager,
        database: SetupDb,
        workers: Optional[int] = None,
        client_factory: Optional[DropboxClientFactory] = None,
        *,
        car_manager: Optional[CarManager] = None,
        track_manager: Optional[TrackManager] = None,
        on_progress: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
        unmatched: Optional[UnmatchedTracker] = None,
    ) -> None:
        super().__init__(
            download_manager,
            dropbox_client,
            workers,
            client_factory,
            car_manager=car_manager if car_manager is not None else setup_manager.car_manager,
            track_manager=track_manager if track_manager is not None else setup_manager.track_manager,
            on_progress=on_progress,
            cancel_event=cancel_event,
            unmatched=unmatched,
        )
        self.setup_manager: SetupManager = setup_manager
        self.database: SetupDb = database
        self.installed_count: int = 0
        self.install_failed_count: int = 0

    # ----- hooks -------------------------------------------------------------

    def _before_publish(self, setup: Setup, original_zip: Path) -> None:
        """The share needs a new version: install locally from the same
        TrackTitan archive the publish worker is about to repackage - no
        round trip through Dropbox."""
        if not self._needs_local_install(setup):
            return
        staged_path: Path = Path(DOWNLOAD_PATH) / f"dual-{setup.id}{original_zip.suffix}"
        try:
            shutil.copy2(original_zip, staged_path)
        except Exception as e:
            self.install_failed_count += 1
            log.error(f"Failed to stage {setup.id} for local install: {e}")
            return
        # The upload's own INSTALL event (emitted by _publish) already marks this
        # setup as done in the activity log; a second one would double-count it.
        self._install_locally(staged_path, setup, sha256=None, emit=False)

    def _on_share_up_to_date(self, setup: Setup, existing: RemoteSetup, current_path: str) -> None:
        """Nothing to publish, but this machine may still lack that version
        (first DUAL run against a share a previous MASTER run filled, a setup
        removed locally, ...). Pull the already-published package from the
        share instead of re-downloading from TrackTitan: unthrottled, and it
        holds the same .svm files."""
        if not self._needs_local_install(setup):
            return
        local_zip: Path = Path(DOWNLOAD_PATH) / existing.name
        try:
            self.dropbox_client.download_to(current_path, local_zip)
            sha256: Optional[str] = sha256_file(local_zip)
        except AuthError:
            # Same policy as _relocate_if_stale_path: an auth failure must reach
            # the GUI's re-authentication dialog, not be swallowed per setup.
            raise
        except Exception as e:
            self.install_failed_count += 1
            log.error(f"Failed to download {setup.id} from the share for local install: {e}")
            return
        self._install_locally(local_zip, setup, sha256=sha256, emit=True)

    # ----- local install -----------------------------------------------------

    def _needs_local_install(self, setup: Setup) -> bool:
        if self.database.is_installed_last_version(setup.id, setup.last_updated):
            log.info("Already installed locally (latest version).")
            return False
        return True

    def _install_locally(self, archive: Path, setup: Setup, sha256: Optional[str], emit: bool) -> bool:
        """Install `archive` via SetupManager.install_setup (DB record included).
        Never raises: a local failure must not stop the publish half or the run."""
        # install_setup rewrites setup.safe_car/safe_track; restore them so the
        # Dropbox path the publish worker derives from them stays exactly what
        # _dispatch resolved, whatever install_setup decided.
        saved_car: str = setup.safe_car
        saved_track: str = setup.safe_track
        try:
            installed: bool = self.setup_manager.install_setup(archive, setup, sha256=sha256)
        except Exception as e:
            self.install_failed_count += 1
            log.error(f"Failed to install {setup.id} locally - {setup.track} - {setup.car}: {e}")
            self._discard_failed_install(archive, setup)
            return False
        finally:
            setup.safe_car = saved_car
            setup.safe_track = saved_track

        if not installed:
            self.install_failed_count += 1
            log.warning(f"Nothing installed locally for {setup.id} - {setup.track} - {setup.car}.")
            return False
        self.installed_count += 1
        log.info(f"Installed {setup.id} locally.")
        if emit:
            self._emit(ProgressEvent(ProgressKind.INSTALL, setup.title, meta=f"{setup.track} - {setup.car}"))
        return True

    def _discard_failed_install(self, archive: Path, setup: Setup) -> None:
        """install_setup raised midway, so its own cleanup never ran: drop the
        half-extracted DOWNLOAD_PATH/<id> folder and, with CLEAN_DOWNLOAD, the
        archive - always this manager's own staged copy or share download, never
        the original the publish worker needs. Safe on the producer thread: this
        id has not been submitted to the pool yet, so no worker extracts there."""
        extraction_path: Path = Path(DOWNLOAD_PATH) / setup.id
        try:
            if extraction_path.exists():
                shutil.rmtree(extraction_path)
            if CLEAN_DOWNLOAD:
                archive.unlink(missing_ok=True)
        except OSError as e:
            log.warning(f"Failed to clean up after the failed local install of {setup.id}: {e}")

    def _report(self, pending: list[tuple[Setup, "Future[bool]"]]) -> None:
        super()._report(pending)
        log.info(
            f"Installed {self.installed_count} setup(s) locally, {self.install_failed_count} failed."
        )
