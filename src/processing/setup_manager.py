import logging
from pathlib import Path
from typing import Optional
import shutil
from core.archive import find_files_recursive, unzip_recursive
from core.config import CLEAN_DOWNLOAD, DOWNLOAD_PATH, OVERWRITE, SETUP_FILE_EXTENSIONS, LMU_SETUPS_BASE_PATH, DELETE_PREVIOUS_VERSION
from domain.setup import Setup
from processing.track_manager import TrackManager
from core.utils import get_path
from domain.setup_db import InstalledSetup, SetupDb

log = logging.getLogger("TrackTitanDownloader")

class SetupManager:
    def __init__(
        self,
        database: SetupDb,
        track_manager: TrackManager,
        lmu_setups_base_path: Optional[Path] = None,
        already_installed : Optional[set[str]] = None,
        overwrite: Optional[bool] = None
    ):
        # Config-backed defaults are resolved here rather than as default arguments,
        # which would freeze them at import time and ignore any later override.
        self.database = database
        self.track_manager = track_manager
        self.lmu_setups_base_path = get_path(lmu_setups_base_path if lmu_setups_base_path is not None else LMU_SETUPS_BASE_PATH)
        self.overwrite = overwrite if overwrite is not None else OVERWRITE
        self.already_installed = already_installed if already_installed is not None else set()
        # Auto-create the configured LMU folder up front (mirrors what
        # core/config.py already does for MOCK_LMU's sandbox path): a fresh LMU
        # install, or a user-edited path that doesn't exist yet, must not fail
        # install_setup() with a path error later on.
        self.lmu_setups_base_path.mkdir(parents=True, exist_ok=True)


    def install_setup(self,downloaded_path: str | Path, setup: Setup) -> None:
        extraction_path = Path(DOWNLOAD_PATH / setup.id)
        if extraction_path.exists(): shutil.rmtree(extraction_path) #To clean previous interrupted elaborations and prevent duplicate file name in extraction
        self._unzip_recursive(downloaded_path, extraction_path)
        (setup_installation_dir, trackFound, matchedTrackId) = self._calculate_setup_installation_dir(setup.track)
        extracted_files: list[Path] = self._copy_file_to_lmu(extraction_path, setup_installation_dir)
        installed: bool = len(extracted_files) > 0
        if not installed: log.warning(f"Setup not installed! Not deleting download for manual installation: {setup.id} - {setup.track} - {setup.car}")
        else:
            if DELETE_PREVIOUS_VERSION: self._cleanup_old(self.database.fetch_setup_files(setup.id),setup_installation_dir, extracted_files)
            self.database.add_installed_setup(setup,extracted_files, trackFound, setup_installation_dir, matchedTrackId)
        self._cleanup_temp(downloaded_path,extraction_path,installed)

    def _unzip_recursive(self, zip_path: str | Path, dest_dir: str | Path) -> None:
        unzip_recursive(zip_path, dest_dir)

    def _find_files_recursive(self, base_dir: str | Path, extensions: set[str]) -> list[Path]:
        return find_files_recursive(base_dir, extensions)

    def _calculate_setup_installation_dir(self, track: str) -> tuple[Path, bool, Optional[str]]:
        track_folder_name = self.track_manager.get_track_folder_name(track)

        if track_folder_name:
            return (self.lmu_setups_base_path / track_folder_name, True, track_folder_name)
        else:
            new_track = f"{track}-HYMO"
            log.warning(f"Track not found in track map: {track}. Will use '-HYMO' track name: {new_track}")
            return (self.lmu_setups_base_path / new_track, False, None)


    def _copy_file_to_lmu(self, extraction_path: str | Path, setup_installation_dir: Path) -> list[Path]:
        extraction_path = get_path(extraction_path)
        files : list[Path] = self._find_files_recursive(extraction_path, SETUP_FILE_EXTENSIONS)

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

    def update_tracks_not_found(self) -> None:
        setups_missing_tracks: list[InstalledSetup] = self.database.fetch_tracks_not_found()
        for setup in setups_missing_tracks:
            self._try_relocate_setup(setup)
        pass

    def _try_relocate_setup(self, setup: InstalledSetup) -> None:
        (setup_installation_dir, track_found, matched_track_id) = self._calculate_setup_installation_dir(setup.track)

        if not track_found:
            log.debug(f"Track still not found in configuration, skipping relocation: {setup.track} for {setup.setup_id}")
            return

        if not setup.installation_base_path:
            log.warning(f"installation_base_path not found in DB for setup: {setup.setup_id}")
            return

        if not setup.installation_folder:
            log.warning(f"installation_folder not found in DB for setup: {setup.setup_id}")
            return

        file_names = self.database.fetch_setup_files(setup.setup_id)
        if not file_names:
            log.warning(f"No files found in DB for setup: {setup.setup_id}")
            return

        old_installation_dir = Path(setup.installation_base_path) / Path(setup.installation_folder)

        moved_files: list[Path] = []
        for file_name in file_names:
            src = old_installation_dir / file_name
            dst = setup_installation_dir / file_name
            if src.exists():
                setup_installation_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), dst)
                moved_files.append(dst)
                log.info(f"Relocated setup file: {src} -> {dst}")
            else:
                log.warning(f"Expected setup file not found during relocation: {src}")

        if moved_files:
            setup.installation_folder = str(setup_installation_dir.name)
            setup.installation_base_path = str(setup_installation_dir.parent)
            setup.track_found = True
            setup.matched_track_id = matched_track_id
            self.database.update_installed_setup(setup)
            log.info(f"Setup relocated successfully: {setup.setup_id} -> {setup_installation_dir}")
            if old_installation_dir.exists() and not any(old_installation_dir.iterdir()):
                try:
                    old_installation_dir.rmdir()
                    log.info(f"Deleted empty old installation directory: {old_installation_dir}")
                except OSError as e:
                    log.warning(f"Could not delete old installation directory {old_installation_dir}: {e}")