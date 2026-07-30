import json
import logging
import shutil
import threading
import zipfile
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from core.archive import METADATA_FILENAME, find_files_recursive, unzip_recursive
from clients.protocols import DropboxClientProtocol
from core.config import CLEAN_DOWNLOAD, DOWNLOAD_PATH, DROPBOX_UPLOAD_WORKERS, SETUP_FILE_EXTENSIONS
from core.errors import AuthError
from core.progress import ProgressCallback, ProgressEvent, ProgressKind
from orchestration.download_manager import DownloadManager
from domain.setup import RemoteSetup, Setup
from domain.unmatched import UnmatchedTracker
from processing.car_manager import CarManager
from processing.track_manager import TrackManager

log = logging.getLogger("TrackTitanDownloader")

DropboxClientFactory = Callable[[], DropboxClientProtocol]


class MasterManager:
    """Publishes TrackTitan setups to a Dropbox share. No DB: the share listing
    is reconciled against the API to decide what to (re)upload.

    The TrackTitan fetch stays serial and throttled on the producer thread - it is
    the only stage the anti-bot delay exists to protect. Everything downstream of
    it (extract, zip, upload, delete) runs on a worker pool, so the Dropbox round
    trips overlap the next setup's throttled download instead of adding to it.
    """

    def __init__(
        self,
        download_manager: DownloadManager,
        dropbox_client: DropboxClientProtocol,
        workers: Optional[int] = None,
        client_factory: Optional[DropboxClientFactory] = None,
        *,
        car_manager: Optional[CarManager] = None,
        track_manager: Optional[TrackManager] = None,
        on_progress: Optional[ProgressCallback] = None,
        cancel_event: Optional[threading.Event] = None,
        unmatched: Optional[UnmatchedTracker] = None,
    ) -> None:
        self.download_manager = download_manager
        # Used for list_setups() on the producer thread, and by the workers too when
        # no factory is given (a mock is safe to share; the real SDK is not).
        self.dropbox_client = dropbox_client
        self.workers: int = max(1, DROPBOX_UPLOAD_WORKERS if workers is None else workers)
        self.client_factory = client_factory
        # Officialize the catalog's raw car/track text against mapping.json before
        # anything derives a Dropbox path from it (see _dispatch) - same resolution
        # SetupManager.install_setup and SlaveManager._process_go already apply on
        # their own side, so the share ends up organized under mapping.json's `name`
        # instead of raw TrackTitan text (e.g. "Oreca 07 (ELMS)", not "Oreca 07
        # Gibson 2024 (ELMS)").
        self.car_manager = car_manager if car_manager is not None else CarManager()
        self.track_manager = track_manager if track_manager is not None else TrackManager()
        self._local = threading.local()
        self._dispatched: set[str] = set()
        self.on_progress = on_progress
        self.cancel_event = cancel_event
        self.unmatched = unmatched if unmatched is not None else UnmatchedTracker()
        # Publish workers may emit concurrently; serialize the calls into on_progress.
        self._progress_lock = threading.Lock()

    def _emit(self, event: ProgressEvent) -> None:
        if self.on_progress is None:
            return
        with self._progress_lock:
            self.on_progress(event)

    def _cancelled(self) -> bool:
        return self.cancel_event is not None and self.cancel_event.is_set()

    def run(self) -> None:
        remote: dict[str, RemoteSetup] = {r.setup_id: r for r in self.dropbox_client.list_setups()}
        log.info(f"Found {len(remote)} setup(s) already on the share.")
        log.info(f"Publishing with {self.workers} upload worker(s).")

        # Bound the packages in flight, so DOWNLOAD_PATH cannot grow without limit
        # if the producer ever outruns the pool.
        slots = threading.Semaphore(self.workers * 2)
        pending: list[tuple[Setup, Future[bool]]] = []

        # "Stop" means stop dispatching new work: it never touches already-submitted
        # tasks, since the `with` block below waits for the pool to drain on exit,
        # letting in-flight publishes finish safely.
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="publish") as pool:
            while not self._cancelled() and (setups := self.download_manager.get_setups_list()):
                for setup in setups:
                    if self._cancelled():
                        break
                    self._dispatch(setup, remote, slots, pool, pending)

        self._report(pending)
        if self._cancelled():
            self._emit(ProgressEvent(ProgressKind.STOPPED, "Publish stopped", unmatched=self.unmatched.serialize()))
        else:
            self._emit(ProgressEvent(ProgressKind.FINISH, "Publish completed", unmatched=self.unmatched.serialize()))

    def _dispatch(
        self,
        setup: Setup,
        remote: dict[str, RemoteSetup],
        slots: threading.Semaphore,
        pool: ThreadPoolExecutor,
        pending: list[tuple[Setup, "Future[bool]"]],
    ) -> None:
        """Runs on the producer thread: every decision that reads shared state, plus
        the throttled TrackTitan download, happens here and stays serial."""
        log.info("#################")
        log.info(setup.title)
        log.info(f"  ID: {setup.id}")

        # Checked before any car/track access: a bundle's combo may not carry a
        # single track/car at all, so reading those first would crash instead
        # of hitting this skip.
        if setup.is_bundle:
            log.info("Skipping bundle.")
            return

        log.info(f"  Car: {setup.car}")
        log.info(f"  Track: {setup.track}")
        self._emit(ProgressEvent(ProgressKind.START, setup.title, meta=f"{setup.track} - {setup.car}"))

        # Some catalog entries carry no car/track identity at all (e.g. certain
        # e-sports/event setups) - there is no raw name for the user to map in
        # this case, so this is skipped outright rather than surfacing a blank
        # entry in the end-of-run correction dialog below.
        if setup.car is None or setup.track is None:
            log.warning(f"Setup missing car/track data, skipping publish: {setup.title}")
            return

        # Resolve mapping.json's official name before anything below reads
        # setup.safe_car/safe_track: both _relocate_if_stale_path and _publish
        # build the Dropbox path from them.
        car_name = self.car_manager.get_car_name(setup.car)
        track_name = self.track_manager.get_official_track_name(setup.track)

        # Unmatched car/track: ignored outright, never uploaded under a raw/
        # placeholder name - recorded for the end-of-run correction dialog
        # instead. Checked before the download, since car/track are already
        # known from the TrackTitan API response.
        if car_name is None or track_name is None:
            log.warning(f"Setup not matched, skipping publish: {setup.track} - {setup.car}")
            self.unmatched.record(
                setup.track, setup.car,
                track_matched=track_name is not None, car_matched=car_name is not None,
            )
            return

        setup.safe_car = car_name
        setup.safe_track = track_name

        # The API can hand back the same id on two pages; the share listing is only
        # read once at startup, so without this it would be published twice.
        if setup.id in self._dispatched:
            log.info("Already published in this run. Skipping.")
            return

        existing: Optional[RemoteSetup] = remote.get(setup.id)
        if existing and existing.ts >= setup.last_updated:
            self._relocate_if_stale_path(setup, existing)
            return

        original_zip = self.download_manager.download(setup)
        if not original_zip:
            log.warning(f"No download produced for {setup.id}. Skipping.")
            return

        self._dispatched.add(setup.id)
        slots.acquire()
        pending.append((setup, pool.submit(self._publish, setup, existing, original_zip, slots)))

    def _relocate_if_stale_path(self, setup: Setup, existing: RemoteSetup) -> None:
        """The setup's content is already current (caller checked existing.ts),
        but it may still sit at an old-layout path - relocate it with a cheap
        server-side move instead of a full re-publish.

        The target keeps existing.name verbatim rather than rebuilding it from
        setup.remote_filename: when the API's last_updated has rolled back below
        what's already published (existing.ts > setup.last_updated), setup's own
        timestamp is stale and would produce the wrong filename. Only the folder
        placement (car/track) is re-derived from the current catalog data.
        """
        target_relative = f"{setup.safe_car}/{setup.safe_track}/{existing.name}"
        target_path = self.dropbox_client.remote_path(target_relative)
        if existing.path_lower.lower() == target_path.lower():
            log.info("Already up to date on share. Skipping.")
            return
        try:
            self.dropbox_client.move(existing.path_lower, target_path)
            log.info(f"Relocated {setup.id} to the unified car/track layout: {target_path}")
        except AuthError:
            # Let this propagate: a swallowed AuthError here (e.g. a token
            # missing the scope files_move_v2 needs) would otherwise never
            # reach gui/api.py's re-authentication dialog, and would just fail
            # silently on every already-published setup for the rest of the run.
            raise
        except Exception as e:
            log.error(f"Failed to relocate {setup.id} to {target_path}: {e}")

    def _publish(
        self,
        setup: Setup,
        existing: Optional[RemoteSetup],
        original_zip: Path,
        slots: threading.Semaphore,
    ) -> bool:
        """Runs on a worker: repackage and publish. Returns whether an upload happened."""
        extraction_path = Path(DOWNLOAD_PATH) / setup.id
        package_path = Path(DOWNLOAD_PATH) / setup.remote_filename
        tag = setup.id[:8]
        try:
            svm_files = self._extract_svm(original_zip, extraction_path)
            if not svm_files:
                log.warning(
                    f"[{tag}] No setup files found for {setup.track} - {setup.car}. Skipping upload."
                )
                return False
            self._build_package(package_path, svm_files, setup)
            client = self._worker_client()
            client.upload(package_path, setup.remote_relative_path)

            # Delete the previous version only AFTER a successful upload, so the
            # share always holds exactly one zip per setup id.
            if existing and existing.name != setup.remote_filename:
                client.delete(existing.path_lower)
                log.info(f"[{tag}] Deleted previous share version: {existing.name}")
            self._emit(ProgressEvent(ProgressKind.INSTALL, setup.title, meta=f"{setup.track} - {setup.car}"))
            return True
        finally:
            self._cleanup(original_zip, extraction_path, package_path)
            slots.release()

    def _worker_client(self) -> DropboxClientProtocol:
        """One Dropbox client per worker thread: the SDK wraps a requests.Session,
        which is not documented as thread-safe."""
        if self.client_factory is None:
            return self.dropbox_client
        client: Optional[DropboxClientProtocol] = getattr(self._local, "client", None)
        if client is None:
            client = self.client_factory()
            self._local.client = client
        return client

    def _report(self, pending: list[tuple[Setup, "Future[bool]"]]) -> None:
        """Drain the futures: a failed worker must be visible, not silently swallowed."""
        uploaded: int = 0
        failed: int = 0
        for setup, future in pending:
            error: Optional[BaseException] = future.exception()
            if error is not None:
                failed += 1
                log.error(f"Failed to publish {setup.id} - {setup.track} - {setup.car}: {error}")
            elif future.result():
                uploaded += 1
        log.info(f"Uploaded {uploaded} setup(s) to the share, {failed} failed.")

    def _extract_svm(self, original_zip: Path, extraction_path: Path) -> list[Path]:
        if extraction_path.exists():
            shutil.rmtree(extraction_path)
        unzip_recursive(original_zip, extraction_path)
        return find_files_recursive(extraction_path, SETUP_FILE_EXTENSIONS)

    def _build_package(self, package_path: Path, svm_files: list[Path], setup: Setup) -> None:
        package_path.parent.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for svm in svm_files:
                if svm.name in seen:
                    continue
                seen.add(svm.name)
                zf.write(svm, arcname=svm.name)
            zf.writestr(METADATA_FILENAME, json.dumps(setup.data))

    def _cleanup(self, original_zip: Optional[Path], extraction_path: Optional[Path], package_path: Optional[Path]) -> None:
        if extraction_path and Path(extraction_path).exists():
            shutil.rmtree(extraction_path)
        if CLEAN_DOWNLOAD:
            for p in (original_zip, package_path):
                if p and Path(p).exists():
                    Path(p).unlink()
