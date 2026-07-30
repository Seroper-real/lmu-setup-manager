import argparse, logging, os, sys, threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.progress import ProgressCallback, ProgressEvent, ProgressKind

LOG_RETENTION_DAYS: int = 7
_CONSOLE_FORMAT = "%(message)s"
_FILE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def _apply_cli_env(argv: Optional[list[str]] = None) -> None:
    """Translate CLI flags into the env vars config.py reads.

    Must run before `config` is imported, since config.py reads the environment at
    import time. A flag only ever *sets* a variable, never clears one, so an
    already-exported MOCK_* still wins: the CLI and the environment compose.

    These flags no longer select a headless execution path (there isn't one): they
    only preconfigure the sandbox/mode state the GUI opens with.
    """
    parser = argparse.ArgumentParser(prog="lmu-setup-manager")
    parser.add_argument("--sandbox", action="store_true", help="mock every external system (TrackTitan, LMU, Dropbox)")
    parser.add_argument("--mock-tracktitan", action="store_true", help="serve setups from the local fixture catalog")
    parser.add_argument("--mock-lmu", action="store_true", help="install into the sandbox folder instead of the game")
    parser.add_argument("--mock-dropbox", action="store_true", help="use a local folder instead of Dropbox")
    parser.add_argument("--mock-base-path", metavar="PATH", help="root for the sandbox directories (default: sandbox)")
    parser.add_argument("--mode", choices=sorted({"full", "master", "slave"}), help="override the mode from config.json")
    args = parser.parse_args(argv)

    if args.sandbox or args.mock_tracktitan:
        os.environ["MOCK_TRACKTITAN"] = "true"
    if args.sandbox or args.mock_lmu:
        os.environ["MOCK_LMU"] = "true"
    if args.sandbox or args.mock_dropbox:
        os.environ["MOCK_DROPBOX"] = "true"
    if args.mock_base_path:
        os.environ["MOCK_BASE_PATH"] = args.mock_base_path
    if args.mode:
        os.environ["MODE"] = args.mode


def _prune_old_logs(logs_dir: Path, max_age_days: int, now: Optional[datetime] = None) -> None:
    """Delete daily log files older than max_age_days. Runs once per app start
    rather than relying on stdlib rotation, so it holds unconditionally - not
    just when a log record happens to be emitted past a rollover time."""
    cutoff = (now or datetime.now()) - timedelta(days=max_age_days)
    for path in logs_dir.glob("app-*.log"):
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
                path.unlink()
        except OSError:
            continue


def setup_logging() -> logging.Logger:
    from core.config import LOG_LEVEL
    from core.utils import get_path

    lvl = logging.getLevelNamesMapping().get(LOG_LEVEL, logging.INFO)

    logger = logging.getLogger("TrackTitanDownloader")
    logger.setLevel(lvl)

    # --- Console Handler (dev-only: invisible in the --windowed packaged exe) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(lvl)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))

    # --- File Handler ---
    logs_dir = get_path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    _prune_old_logs(logs_dir, LOG_RETENTION_DAYS)

    log_path = logs_dir / f"app-{datetime.now():%Y-%m-%d}.log"
    file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
    file_handler.setLevel(lvl)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))

    if logger.hasHandlers():
        logger.handlers.clear()

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def apply_log_level(level: str) -> None:
    """Re-apply a new level to the already-attached handlers in place, so a
    Settings save takes effect immediately (mirrors gui/api.py's
    _reload_config(), which hot-reloads every other setting the same way)."""
    lvl = logging.getLevelNamesMapping().get(level.strip().upper(), logging.INFO)
    logger = logging.getLogger("TrackTitanDownloader")
    logger.setLevel(lvl)
    for handler in logger.handlers:
        handler.setLevel(lvl)


def _log_sandbox(log: logging.Logger) -> None:
    """Record in every log whether this run touched the real world."""
    from core.config import MOCK_TRACKTITAN, MOCK_LMU, MOCK_DROPBOX, SANDBOX_ENABLED

    if not SANDBOX_ENABLED:
        return
    active = [
        name for name, on in (
            ("TrackTitan", MOCK_TRACKTITAN),
            ("LMU", MOCK_LMU),
            ("Dropbox", MOCK_DROPBOX),
        ) if on
    ]
    log.warning(f"SANDBOX ACTIVE - faking: {', '.join(active)}")


def run_full(
    log: logging.Logger,
    *,
    on_progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    from domain.setup_db import SetupDb
    from domain.unmatched import UnmatchedTracker
    from processing.car_manager import CarManager
    from processing.track_manager import TrackManager
    from orchestration.download_manager import DownloadManager
    from processing.setup_manager import SetupManager
    from clients.protocols import build_track_titan_client

    database = SetupDb()
    track_manager = TrackManager()
    car_manager = CarManager()
    download_manager = DownloadManager(database=database, client=build_track_titan_client(), cancel_event=cancel_event)
    setup_manager = SetupManager(track_manager=track_manager, car_manager=car_manager, database=database)
    unmatched = UnmatchedTracker()

    def _emit(event: ProgressEvent) -> None:
        if on_progress is not None:
            on_progress(event)

    # The TrackTitan API can hand back the same id on two adjacent pages (see
    # MasterManager._dispatch's own _dispatched set for the same guard) - without
    # this, that setup would be downloaded and installed twice in one run.
    dispatched: set[str] = set()

    while setups := download_manager.get_setups_list():
        for setup in setups:
            if cancel_event is not None and cancel_event.is_set():
                _emit(ProgressEvent(ProgressKind.STOPPED, "Download stopped", unmatched=unmatched.serialize()))
                return

            if setup.id in dispatched:
                log.info(f"Already processed in this run, skipping duplicate page entry: {setup.id}")
                continue
            dispatched.add(setup.id)

            log.info(f"#################")
            log.info(f"{setup.title}")
            log.info(f"  ID: {setup.id}")

            # Checked before any car/track access: a bundle's combo may not
            # carry a single track/car at all, so reading those first would
            # crash instead of hitting this skip.
            if setup.is_bundle:
                log.info(f"Skipping bundle.")
                continue  # Non scarichiamo i bundle

            log.info(f"  Car: {setup.car}")
            log.info(f"  Track: {setup.track}")
            _emit(ProgressEvent(ProgressKind.START, setup.title, meta=f"{setup.track} - {setup.car}"))

            # Some catalog entries carry no car/track identity at all (e.g.
            # certain e-sports/event setups) - there is no raw name for the
            # user to map in this case, so this is skipped outright rather
            # than surfacing a blank entry in the correction dialog below.
            if setup.car is None or setup.track is None:
                log.warning(f"Setup missing car/track data, skipping: {setup.title}")
                continue

            # Unmatched car/track: ignored outright, never installed under a
            # placeholder "-HYMO" name - recorded for the end-of-run
            # correction dialog instead. Checked before the download, since
            # car/track are already known from the TrackTitan API response.
            car_name = car_manager.get_car_name(setup.car)
            track_name = track_manager.get_official_track_name(setup.track)
            if car_name is None or track_name is None:
                log.warning(f"Setup not matched, skipping: {setup.track} - {setup.car}")
                unmatched.record(
                    setup.track, setup.car,
                    track_matched=track_name is not None, car_matched=car_name is not None,
                )
                continue

            path = download_manager.download(setup)

            if path:
                setup_manager.install_setup(path, setup)
                _emit(ProgressEvent(ProgressKind.INSTALL, setup.title, meta=f"{setup.track} - {setup.car}"))

    _emit(ProgressEvent(ProgressKind.FINISH, "Download completed", unmatched=unmatched.serialize()))


def run_master(
    log: logging.Logger,
    *,
    on_progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    from domain.unmatched import UnmatchedTracker
    from orchestration.download_manager import DownloadManager
    from orchestration.master_manager import MasterManager
    from processing.car_manager import CarManager
    from processing.track_manager import TrackManager
    from clients.protocols import build_dropbox_client, build_track_titan_client

    download_manager = DownloadManager(database=None, client=build_track_titan_client(), cancel_event=cancel_event)
    dropbox_client = build_dropbox_client()
    # The factory gives each upload worker its own client instead of sharing one.
    MasterManager(
        download_manager=download_manager,
        dropbox_client=dropbox_client,
        client_factory=build_dropbox_client,
        car_manager=CarManager(),
        track_manager=TrackManager(),
        on_progress=on_progress,
        cancel_event=cancel_event,
        unmatched=UnmatchedTracker(),
    ).run()


def run_slave(
    log: logging.Logger,
    *,
    on_progress: Optional[ProgressCallback] = None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    from domain.setup_db import SetupDb
    from domain.unmatched import UnmatchedTracker
    from processing.car_manager import CarManager
    from processing.track_manager import TrackManager
    from processing.setup_manager import SetupManager
    from orchestration.slave_manager import SlaveManager
    from clients.protocols import build_dropbox_client

    database = SetupDb()
    track_manager = TrackManager()
    car_manager = CarManager()
    setup_manager = SetupManager(track_manager=track_manager, car_manager=car_manager, database=database)
    dropbox_client = build_dropbox_client()
    SlaveManager(
        dropbox_client=dropbox_client,
        setup_manager=setup_manager,
        database=database,
        on_progress=on_progress,
        cancel_event=cancel_event,
        unmatched=UnmatchedTracker(),
    ).run()


if __name__ == "__main__":
    _apply_cli_env()
    from gui.window import launch
    launch()
