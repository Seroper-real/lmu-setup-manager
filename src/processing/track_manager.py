import json
import re
import unicodedata
import requests
import logging
from core.config import REMOTE_TRACKS_ENABLED, REMOTE_TRACKS_TIMEOUT, REMOTE_TRACKS_URL
from core.utils import get_path
from core import settings_db

log = logging.getLogger("TrackTitanDownloader")

class TrackManager:
    """Two-layer track matcher: config/tracks.json (dev-maintained, pushed to the
    repo/remote mirror without a release) first, then settings.db's per-user
    "Correggi" customizations, then -HYMO (handled by callers on a None result).
    """

    def __init__(self) -> None:
        self.tracks_json_path = get_path("config/tracks.json")
        self.active_json: dict = {}
        self.file_track_patterns: list[tuple[re.Pattern[str], str]] = []
        self.custom_track_patterns: list[tuple[re.Pattern[str], str]] = []
        self.refresh()

    def _normalize_track(self, track: str) -> str:
        return unicodedata.normalize("NFC", track).strip()

    def _load_local_tracks(self) -> dict | None:
        if self.tracks_json_path.exists():
            with open(self.tracks_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else: return None

    def _load_remote_tracks(self) -> dict | None:
        if REMOTE_TRACKS_ENABLED:
            try:
                response = requests.get(REMOTE_TRACKS_URL, timeout=REMOTE_TRACKS_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                log.error(f"Cannot download tracks file from Github. Error: {e}")
        return None

    @staticmethod
    def _compile_patterns(tracks_data: list[dict]) -> list[tuple[re.Pattern[str], str]]:
        patterns: list[tuple[re.Pattern[str], str]] = []
        for track in tracks_data:
            lmu_folder: str = track["lmu_folder_name"]
            for raw_pattern in track.get("tt_patterns", []):
                try:
                    compiled = re.compile(raw_pattern, re.IGNORECASE)
                    patterns.append((compiled, lmu_folder))
                except re.error as e:
                    log.warning(f"Invalid regex pattern '{raw_pattern}' for track '{lmu_folder}': {e}. Skipping.")
        return patterns

    def build_track_patterns(self) -> None:
        # No versioning: the dev maintains a single canonical tracks.json, pushed to
        # the remote mirror without a release. Remote wins whenever it's reachable;
        # the bundled local file is only an offline/disabled-remote fallback.
        remote_json = self._load_remote_tracks()
        local_json = self._load_local_tracks()

        if remote_json is not None:
            log.info("Using remote tracks mapping file")
            self.active_json = remote_json
        elif local_json is not None:
            log.info("Using local tracks mapping file")
            self.active_json = local_json
        else:
            raise RuntimeError("No tracks mapping file found. Both local and remote files are missing or inaccessible.")

        self.file_track_patterns = self._compile_patterns(self.active_json.get("tracks", []))
        self.custom_track_patterns = self._compile_patterns(settings_db.get_custom_tracks())

    def get_track_folder_name(self, track: str) -> str | None:
        # First-match-wins: file-derived patterns first, then per-user DB
        # customizations, then None (callers fall back to the -HYMO suffix).
        normalized = self._normalize_track(track)
        for pattern, lmu_folder in self.file_track_patterns:
            if pattern.search(normalized):
                return lmu_folder
        for pattern, lmu_folder in self.custom_track_patterns:
            if pattern.search(normalized):
                return lmu_folder
        return None

    def get_known_folder_names(self) -> list[str]:
        # Sorted, de-duplicated lmu_folder_name values, for the GUI's "Correggi" <select>.
        file_names = {track["lmu_folder_name"] for track in self.active_json.get("tracks", [])}
        return sorted(file_names | set(settings_db.get_custom_folder_names()))

    def add_or_update_mapping(self, track: str, lmu_folder_name: str) -> None:
        settings_db.upsert_track_pattern(lmu_folder_name, re.escape(track))

    def refresh(self) -> None:
        # Rebuild from the now-updated file/DB. A plain attribute reassignment: safe
        # under the GIL, no lock needed.
        self.build_track_patterns()
