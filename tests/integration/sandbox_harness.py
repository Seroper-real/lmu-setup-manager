"""Shared harness for sandbox-backed integration tests.

Everything below drives the *real* DownloadManager / MasterManager / SlaveManager /
SetupManager / TrackManager and the real archive extraction. Only the three external
systems are replaced: the TrackTitan API, the Dropbox share and the LMU game folder.
"""
import json
import zipfile
from pathlib import Path
from typing import Optional


# The fixtures shipped with the app, used by tests that assert on them specifically.
REPO_FIXTURES: Path = Path(__file__).resolve().parents[2] / "sandbox" / "tracktitan"


def make_setup(
    setup_id: str,
    track: str,
    car: str = "Porsche 963",
    ts: int = 1700000000,
    is_bundle: bool = False,
    title: Optional[str] = None,
) -> dict:
    """One entry of the TrackTitan /setups payload."""
    return {
        "id": setup_id,
        "title": title or f"Setup for {track}",
        "setupCombos": [{"car": {"name": car}, "track": {"name": track}}],
        "hotlapLink": None,
        "lastUpdatedAt": ts,
        "isBundle": is_bundle,
    }


class Sandbox:
    """A disposable app root: mock catalog, mock share, mock game folder."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.downloads = root / "downloads"
        self.share = root / "share"
        self.lmu = root / "lmu"
        self.catalog_dir = root / "tracktitan"
        self.tracks_file = root / "tracks.json"

        self.downloads.mkdir(parents=True, exist_ok=True)
        self.lmu.mkdir(parents=True, exist_ok=True)
        (self.catalog_dir / "setups").mkdir(parents=True, exist_ok=True)

        self._tracks_mapping: list[tuple[str, str]] = []
        # make_setup()'s own default car is "Porsche 963" - seeded here so
        # this harness's overwhelmingly track-focused tests don't each need
        # their own boilerplate set_cars() call just to keep that one default
        # car resolvable now that an unmatched car blocks install/publish
        # just like an unmatched track does. A test using a different car
        # calls set_cars() itself, same as it already does for set_tracks().
        self._cars_mapping: list[tuple[str, str]] = [("963", "Porsche 963")]

        self.write_catalog([])
        self._write_mapping()

    # ----- fixture authoring -------------------------------------------------

    def write_catalog(self, setups: list[dict]) -> None:
        (self.catalog_dir / "catalog.json").write_text(
            json.dumps({"data": {"setups": setups}}), encoding="utf-8"
        )

    def add_archive(self, setup_id: str, members: dict[str, str]) -> Path:
        """Write sandbox/tracktitan/setups/{id}.zip holding the given members."""
        path = self.catalog_dir / "setups" / f"{setup_id}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        return path

    def add_go_zip(self, car: str, track: str, zip_name: str, members: dict[str, str]) -> Path:
        """Write share/{car}/{track}/{zip_name} - a manually-uploaded GO Setups
        archive, mirroring the unified layout (no separate GO/ marker level)."""
        path = self.share / car / track / zip_name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in members.items():
                zf.writestr(name, content)
        return path

    def add_manual_hymo_zip(self, car: str, track: str, members: dict[str, str]):
        """Publish a manually-uploaded HYMO-type archive to the mock share by
        driving the real build_manual_setup()/upload_manual_setup_to_dropbox()
        (master-mode Upload tab code path) instead of hand-crafting a fixture,
        so tests exercise the exact packaging a live manual upload produces.
        Returns the synthetic Setup that was uploaded, for id/timestamp
        assertions."""
        from processing.manual_upload import build_manual_setup, upload_manual_setup_to_dropbox

        setup = build_manual_setup(track, car)
        staging = self.root / "manual_upload_source"
        staging.mkdir(parents=True, exist_ok=True)
        source_zip = staging / f"{setup.id}.zip"
        with zipfile.ZipFile(source_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in members.items():
                zf.writestr(name, content)

        upload_manual_setup_to_dropbox(self.dropbox(), source_zip, setup, "HYMO")
        return setup

    def _write_mapping(self) -> None:
        """tracks_file backs both TrackManager and CarManager in the sandbox
        fixture (see tests/integration/conftest.py), so a track and a car
        write must land in the same file - one combined writer for both."""
        self.tracks_file.write_text(
            json.dumps({
                "tracks": [{"name": f, "matcher": [p], "lmu_folder": f} for p, f in self._tracks_mapping],
                "cars": [{"name": n, "matcher": [p]} for p, n in self._cars_mapping],
            }),
            encoding="utf-8",
        )

    def set_tracks(self, mapping: list[tuple[str, str]]) -> None:
        """mapping is a list of (regex pattern, lmu folder name), in priority order."""
        self._tracks_mapping = mapping
        self._write_mapping()

    def set_cars(self, mapping: list[tuple[str, str]]) -> None:
        """mapping is a list of (regex pattern, official car name), in
        priority order - same shape as set_tracks(). Replaces (does not merge
        with) the default "963" -> "Porsche 963" seed from __init__, so a
        test using a non-default car alongside the default one must list
        both explicitly."""
        self._cars_mapping = mapping
        self._write_mapping()

    # ----- inspection --------------------------------------------------------

    def installed_files(self) -> set[str]:
        """Every installed file, as posix paths relative to the mock LMU root."""
        return {p.relative_to(self.lmu).as_posix() for p in self.lmu.rglob("*") if p.is_file()}

    def share_names(self) -> set[str]:
        return {p.name for p in self.share.glob("**/*.zip")} if self.share.exists() else set()

    # ----- clients -----------------------------------------------------------

    def tracktitan(self, base_path: Optional[Path] = None):
        from clients.mocks.mock_track_titan_client import MockTrackTitanClient
        return MockTrackTitanClient(base_path=base_path or self.catalog_dir)

    def dropbox(self):
        from clients.mocks.mock_dropbox_client import MockDropboxClient
        return MockDropboxClient(folder=self.share)

    # ----- orchestrators -----------------------------------------------------

    def run_master(self, base_path: Optional[Path] = None):
        from orchestration.download_manager import DownloadManager
        from orchestration.master_manager import MasterManager
        from processing.track_manager import TrackManager
        from processing.car_manager import CarManager

        dbx = self.dropbox()
        dm = DownloadManager(database=None, client=self.tracktitan(base_path))
        MasterManager(
            download_manager=dm, dropbox_client=dbx,
            car_manager=CarManager(), track_manager=TrackManager(),
        ).run()
        return dbx

    def run_slave(self, database) -> None:
        from orchestration.slave_manager import SlaveManager
        SlaveManager(
            dropbox_client=self.dropbox(),
            setup_manager=self.setup_manager(database),
            database=database,
        ).run()

    def run_full(self, database, base_path: Optional[Path] = None) -> None:
        """Mirrors main.run_full: paginate, skip bundles, download, install."""
        from orchestration.download_manager import DownloadManager

        dm = DownloadManager(database=database, client=self.tracktitan(base_path))
        sm = self.setup_manager(database)

        while setups := dm.get_setups_list():
            for setup in setups:
                if setup.is_bundle:
                    continue
                path = dm.download(setup)
                if path:
                    sm.install_setup(path, setup)

    def setup_manager(self, database):
        from processing.setup_manager import SetupManager
        from processing.track_manager import TrackManager
        from processing.car_manager import CarManager

        return SetupManager(
            database=database,
            track_manager=TrackManager(),
            car_manager=CarManager(),
            lmu_setups_base_path=self.lmu,
        )
