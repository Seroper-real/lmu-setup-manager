import logging
from pathlib import Path
from typing import Optional
import shutil
from core.archive import find_files_recursive, unzip_recursive
from core.config import CLEAN_DOWNLOAD, DOWNLOAD_PATH, OVERWRITE, SETUP_FILE_EXTENSIONS, LMU_SETUPS_BASE_PATH, DELETE_PREVIOUS_VERSION
from domain.setup import Setup
from processing.car_manager import CarManager
from processing.track_manager import TrackManager
from core.utils import get_path
from domain.setup_db import SetupDb

log = logging.getLogger("TrackTitanDownloader")

class SetupManager:
    def __init__(
        self,
        database: SetupDb,
        track_manager: TrackManager,
        car_manager: CarManager,
        lmu_setups_base_path: Optional[Path] = None,
        already_installed : Optional[set[str]] = None,
        overwrite: Optional[bool] = None
    ):
        # Config-backed defaults are resolved here rather than as default arguments,
        # which would freeze them at import time and ignore any later override.
        self.database = database
        self.track_manager = track_manager
        self.car_manager = car_manager
        self.lmu_setups_base_path = get_path(lmu_setups_base_path if lmu_setups_base_path is not None else LMU_SETUPS_BASE_PATH)
        self.overwrite = overwrite if overwrite is not None else OVERWRITE
        self.already_installed = already_installed if already_installed is not None else set()
        # Auto-create the configured LMU folder up front (mirrors what
        # core/config.py already does for MOCK_LMU's sandbox path): a fresh LMU
        # install, or a user-edited path that doesn't exist yet, must not fail
        # install_setup() with a path error later on.
        self.lmu_setups_base_path.mkdir(parents=True, exist_ok=True)


    def install_setup(
        self,
        downloaded_path: str | Path,
        setup: Setup,
        extensions: Optional[set[str]] = None,
        setup_type: str = "HYMO",
        sha256: Optional[str] = None,
    ) -> bool:
        """Returns False (without touching the DB or the LMU folder) when the
        setup's car or track doesn't resolve against mapping.json + the
        manual_mapping fallback - an unmatched setup is ignored outright, not
        installed under a placeholder "-HYMO"/"-GO" name. This is the
        authoritative, last-resort check: callers upstream (run_full,
        MasterManager, SlaveManager) also pre-check for efficiency (so an
        unmatched setup is never even downloaded when its identity is known
        ahead of time), but this is what guarantees the invariant regardless."""
        setup_installation_dir = self._calculate_setup_installation_dir(setup.track)
        car_name = self.car_manager.get_car_name(setup.car)
        if setup_installation_dir is None or car_name is None:
            log.warning(f"Setup not matched, skipping: {setup.track} - {setup.car}")
            if CLEAN_DOWNLOAD:
                Path(downloaded_path).unlink(missing_ok=True)
            return False

        track_folder_name = setup_installation_dir.name
        setup.safe_track = self.track_manager.get_official_track_name(setup.track) or track_folder_name
        setup.safe_car = car_name

        extraction_path = Path(DOWNLOAD_PATH / setup.id)
        if extraction_path.exists(): shutil.rmtree(extraction_path) #To clean previous interrupted elaborations and prevent duplicate file name in extraction
        self._unzip_recursive(downloaded_path, extraction_path)
        extracted_files: list[Path] = self._copy_file_to_lmu(extraction_path, setup_installation_dir, extensions)
        installed: bool = len(extracted_files) > 0
        if not installed: log.warning(f"Setup not installed! Not deleting download for manual installation: {setup.id} - {setup.track} - {setup.car}")
        else:
            if DELETE_PREVIOUS_VERSION:
                self._cleanup_old(self.database.fetch_setup_files(setup.id),setup_installation_dir, extracted_files)
            self.database.add_installed_setup(
                setup, extracted_files, True, setup_installation_dir, track_folder_name,
                setup_type=setup_type, sha256=sha256,
            )
        self._cleanup_temp(downloaded_path,extraction_path,installed)
        return True

    def _unzip_recursive(self, zip_path: str | Path, dest_dir: str | Path) -> None:
        unzip_recursive(zip_path, dest_dir)

    def _find_files_recursive(self, base_dir: str | Path, extensions: set[str]) -> list[Path]:
        return find_files_recursive(base_dir, extensions)

    def _calculate_setup_installation_dir(self, track: str) -> Optional[Path]:
        track_folder_name = self.track_manager.get_track_folder_name(track)
        return (self.lmu_setups_base_path / track_folder_name) if track_folder_name else None


    def _copy_file_to_lmu(self, extraction_path: str | Path, setup_installation_dir: Path, extensions: Optional[set[str]] = None) -> list[Path]:
        extraction_path = get_path(extraction_path)
        exts = extensions if extensions is not None else SETUP_FILE_EXTENSIONS
        files : list[Path] = self._find_files_recursive(extraction_path, exts)

        setup_installation_dir.mkdir(parents=True, exist_ok=True) 

        for file in files:
            file_path = get_path(file)

            dest_file_path = setup_installation_dir / file_path.name
            if dest_file_path.exists() and not self.overwrite:
                log.warning(f"Setup already exists and overwrite is disabled: {dest_file_path}")
            else:
                shutil.copy2(file_path, dest_file_path)
                log.info(f"Copied setup to LMU: {dest_file_path}")

        return files

    def _cleanup_temp(self, downloaded_path: str | Path, extraction_path:str | Path, installed: bool) -> None:
        downloaded_path = Path(downloaded_path)
        extraction_path = Path(extraction_path)

        if extraction_path.exists(): 
            shutil.rmtree(extraction_path)
            log.debug(f"Deleted: {extraction_path}")

        if CLEAN_DOWNLOAD and installed and downloaded_path.exists(): 
            downloaded_path.unlink()
            log.debug(f"Deleted: {downloaded_path}")
        log.info("Cleanup completed")

    def _cleanup_old(self,old_setups: list[str],setup_installation_dir: Path, extracted_files: list[Path]) -> None:
        #Important! Must not delete if extracted_files has same name as old_setups
        extracted_names = [x.name for x in extracted_files]
        to_be_deleted = [x for x in old_setups if x not in extracted_names]

        for old_setup in to_be_deleted:
            old_setup_path = setup_installation_dir / old_setup
            if old_setup_path.exists():
                old_setup_path.unlink()
                log.info(f"Deleted previous setup: {old_setup_path}")

    def delete_setup(self, setup_id: str) -> bool:
        setup = self.database.fetch_installed_setup(setup_id)
        if setup is None:
            return False

        if setup.installation_base_path and setup.installation_folder:
            install_dir = Path(setup.installation_base_path) / setup.installation_folder
            for file_name in setup.file_names:
                file_path = install_dir / file_name
                try:
                    file_path.unlink()
                    log.info(f"Deleted setup file: {file_path}")
                except FileNotFoundError:
                    log.warning(f"Setup file already missing on disk, skipping: {file_path}")
            if install_dir.exists() and not any(install_dir.iterdir()):
                try:
                    install_dir.rmdir()
                    log.info(f"Deleted empty installation directory: {install_dir}")
                except OSError as e:
                    log.warning(f"Could not delete empty installation directory {install_dir}: {e}")

        self.database.delete_installed_setup(setup_id)
        log.info(f"Removed installed setup from database: {setup_id}")
        return True