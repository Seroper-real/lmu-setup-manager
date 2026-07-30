import json
import logging
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from clients.protocols import DropboxClientProtocol
from core.archive import METADATA_FILENAME, find_files_recursive, sha256_file, unzip_recursive
from core.config import CLEAN_DOWNLOAD, DOWNLOAD_PATH, GO_SETUP_FILE_EXTENSIONS, SETUP_FILE_EXTENSIONS
from domain.setup import Setup
from processing.car_manager import CarManager
from processing.setup_manager import SetupManager
from processing.track_manager import TrackManager

log = logging.getLogger("TrackTitanDownloader")


def guess_car_track_from_filename(
    file_name: str, car_manager: CarManager, track_manager: TrackManager
) -> tuple[Optional[str], Optional[str]]:
    """Best-effort (car, lmu_folder) guess for the Upload tab's dropdowns from
    a picked/dropped file's name, e.g. "GO-FERRARI-499P-SEBRING.zip" ->
    ("Ferrari 499P", "Sebring").

    Reuses mapping.json's own car/track matchers (see CarManager.get_car_name,
    TrackManager.get_track_folder_name): those are already substring regexes
    meant to recognize a known name inside arbitrary raw text (TrackTitan's
    own combo strings), so searching the same patterns against the raw
    filename stem works without any bespoke parsing - no attempt is made to
    split the name into car/track segments, since a car name can itself
    contain the separators (spaces, hyphens) used between segments.
    """
    stem = Path(file_name).stem
    return car_manager.get_car_name(stem), track_manager.get_track_folder_name(stem)


def build_manual_setup(track: str, car: str) -> Setup:
    """A synthetic Setup for a manually-uploaded archive - no TrackTitan
    metadata of its own, built the same way SlaveManager._process_go builds
    one for a GO Setups archive it finds on the share."""
    setup = Setup({
        "id": str(uuid.uuid4()),
        "title": f"{car} - {track}",
        "setupCombos": [{"car": {"name": car}, "track": {"name": track}}],
        "hotlapLink": None,
        "lastUpdatedAt": int(time.time() * 1000),
        "isBundle": False,
    })
    # track/car come straight from the Upload tab's dropdowns, themselves built
    # from mapping.json's own `name`/lmu_folder values (see CarManager.get_all_cars,
    # TrackManager.get_known_folder_names) - already-official identities, not raw
    # TrackTitan text. Assigned to safe_track/safe_car directly, bypassing Setup's
    # default sanitize_identity normalization (which would mangle a hyphen or slash
    # in an official name, e.g. "Cadillac V-Series.R"), so the Dropbox folder this
    # setup publishes under matches mapping.json's `name` field exactly - the same
    # unsanitized assignment SetupManager.install_setup does once it resolves an
    # official name for a regular (non-manual) setup.
    setup.safe_track = track
    setup.safe_car = car
    return setup


def _extensions_for(setup_type: str) -> set[str]:
    return GO_SETUP_FILE_EXTENSIONS if setup_type == "GO" else SETUP_FILE_EXTENSIONS


def install_manual_setup_locally(
    setup_manager: SetupManager, zip_path: str | Path, setup: Setup, setup_type: str
) -> None:
    """Stage a copy under DOWNLOAD_PATH before installing: install_setup()
    takes ownership of its downloaded_path argument (and may delete it, per
    CLEAN_DOWNLOAD) - handing it the user's own original file directly would
    risk deleting something they still have elsewhere on disk."""
    # A second manual upload for the same car/track/type is an update, not a
    # new setup: reuse the previous row's id so install_setup()'s upsert (and
    # its DELETE_PREVIOUS_VERSION cleanup) replace it in place instead of
    # installing a duplicate alongside it - same identity model SlaveManager
    # already applies to GO Setups (car+track+type, no stable external id).
    existing = setup_manager.database.fetch_installed_setup_by_identity(setup.safe_car, setup.safe_track, setup_type)
    if existing:
        setup.data["id"] = existing.setup_id

    staged_path = Path(DOWNLOAD_PATH) / f"manual-{setup.id}{Path(zip_path).suffix}"
    shutil.copy2(zip_path, staged_path)
    sha256 = sha256_file(staged_path)
    setup_manager.install_setup(
        staged_path, setup, extensions=_extensions_for(setup_type), setup_type=setup_type,
        sha256=sha256,
    )
    log.info(f"Manually installed setup: {setup.car} - {setup.track} ({setup_type})")


def upload_manual_setup_to_dropbox(
    dropbox_client: DropboxClientProtocol, zip_path: str | Path, setup: Setup, setup_type: str
) -> None:
    if setup_type == "GO":
        _upload_go_setup(dropbox_client, zip_path, setup)
    else:
        _upload_hymo_setup(dropbox_client, zip_path, setup)


def _upload_go_setup(dropbox_client: DropboxClientProtocol, zip_path: str | Path, setup: Setup) -> None:
    """GO Setups archives are consumed by SlaveManager._process_go purely from
    their <Car>/<Track>/<file>.zip share position and a GO-prefixed filename
    (see domain/go_setup.py) - the original setup files are never repackaged,
    only copied (never the user's own original, which is left untouched) and
    given an embedded .metadata.json alongside them, same as _upload_hymo_setup
    below. Ignored on install by the .svm/.ld/.ldx-only extraction filter
    (METADATA_FILENAME's .json suffix never matches GO_SETUP_FILE_EXTENSIONS),
    so this is purely informational: it lets a manually-uploaded GO setup
    carry the same "when was this last touched" metadata a HYMO one already
    does, without changing how SlaveManager decides whether to (re)install it
    (still the sha256 content check).

    The uploaded filename itself is rebuilt from setup.go_filename rather than
    kept from the user's original archive, so it carries the same id/date
    info a HYMO archive's remote_filename does (only GO- branded instead of
    HYMO-) - only car/track are borrowed from Setup.safe_car/safe_track, same
    as MasterManager's own folder layout.

    A second manual upload for the same car/track is an update: GO identity
    is the car/track folder itself (there is no stable id to key off, see
    domain/go_setup.py's RemoteGoSetup), so the previous archive there is
    deleted right after the new one lands - same "upload new, then delete
    old" ordering MasterManager._publish uses for HYMO.
    """
    zip_path = Path(zip_path)
    existing = dropbox_client.find_existing_setup(setup.safe_car, setup.safe_track, "GO")
    filename = setup.go_filename
    staged_path = Path(DOWNLOAD_PATH) / f"manual-go-{setup.id}{zip_path.suffix}"
    try:
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(zip_path, staged_path)
        with zipfile.ZipFile(staged_path, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(METADATA_FILENAME, json.dumps(setup.data))

        remote_relative_path = f"{setup.safe_car}/{setup.safe_track}/{filename}"
        dropbox_client.upload(staged_path, remote_relative_path)
        if existing and existing.name != filename:
            dropbox_client.delete(existing.path_lower)
            log.info(f"Deleted previous manual GO Setup version: {existing.name}")
        log.info(f"Manually published GO Setup to Dropbox: {remote_relative_path}")
    finally:
        if CLEAN_DOWNLOAD and staged_path.exists():
            staged_path.unlink()


def _upload_hymo_setup(dropbox_client: DropboxClientProtocol, zip_path: str | Path, setup: Setup) -> None:
    """Repackage and publish, mirroring MasterManager._publish/_build_package:
    a fresh zip holding only the recognized setup files plus an embedded
    .metadata.json, uploaded under the HYMO- branded car/track layout -
    exactly what SlaveManager._process expects to read back.

    A second manual upload for the same car/track is an update: reuse the
    previously-published archive's id (there being no stable TrackTitan id to
    key off for a manual upload otherwise) so the new package keeps the same
    id with only its date changing, exactly as SlaveManager._process expects
    to recognize a newer version of the same setup. The stale package is
    deleted only after the new one lands, same ordering MasterManager._publish
    uses.
    """
    existing = dropbox_client.find_existing_setup(setup.safe_car, setup.safe_track, "HYMO")
    if existing and existing.setup_id:
        setup.data["id"] = existing.setup_id

    extraction_path = Path(DOWNLOAD_PATH) / f"manual-{setup.id}-extract"
    package_path = Path(DOWNLOAD_PATH) / setup.remote_filename
    try:
        if extraction_path.exists():
            shutil.rmtree(extraction_path)
        unzip_recursive(zip_path, extraction_path)
        setup_files = find_files_recursive(extraction_path, SETUP_FILE_EXTENSIONS)
        if not setup_files:
            raise ValueError(
                f"No recognized setup files ({', '.join(sorted(SETUP_FILE_EXTENSIONS))}) found in the uploaded archive."
            )

        package_path.parent.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in setup_files:
                if f.name in seen:
                    continue
                seen.add(f.name)
                zf.write(f, arcname=f.name)
            zf.writestr(METADATA_FILENAME, json.dumps(setup.data))

        dropbox_client.upload(package_path, setup.remote_relative_path)
        if existing and existing.name != setup.remote_filename:
            dropbox_client.delete(existing.path_lower)
            log.info(f"Deleted previous manual HYMO Setup version: {existing.name}")
        log.info(f"Manually published HYMO setup to Dropbox: {setup.remote_relative_path}")
    finally:
        if extraction_path.exists():
            shutil.rmtree(extraction_path)
        if CLEAN_DOWNLOAD and package_path.exists():
            package_path.unlink()
