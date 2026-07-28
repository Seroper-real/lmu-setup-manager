import re
import unicodedata
import logging
from core.config import REMOTE_MAPPINGS_ENABLED, REMOTE_MAPPINGS_TIMEOUT, REMOTE_MAPPINGS_URL
from core.utils import get_path
from core import settings_db
from processing.catalog_loader import compile_patterns, load_catalog_with_fallback

log = logging.getLogger("TrackTitanDownloader")

class TrackManager:
    """Two-layer track matcher: config/mapping.json's "tracks" section
    (dev-maintained, pushed to the repo/remote mirror without a release)
    first, then settings.db's manual_mapping "Correggi"/unmatched-setup
    customizations (type="track"). A None result means the setup is skipped
    entirely by callers (see SetupManager.install_setup, MasterManager,
    SlaveManager) rather than falling back to a placeholder name.

    `name` (the official, app-wide track identity) and `lmu_folder` (the
    physical LMU installation folder) are resolved independently from the
    same matcher patterns - they coincide for every entry in mapping.json
    today, but are conceptually distinct fields (see get_official_track_name
    vs get_track_folder_name).
    """

    def __init__(self) -> None:
        self.mapping_json_path = get_path("config/mapping.json")
        self.file_track_name_patterns: list[tuple[re.Pattern[str], str]] = []
        self.file_track_folder_patterns: list[tuple[re.Pattern[str], str]] = []
        self.custom_track_patterns: list[tuple[re.Pattern[str], str]] = []
        self._track_entries: list[dict] = []
        self.refresh()

    def _normalize_track(self, track: str) -> str:
        return unicodedata.normalize("NFC", track).strip()

    def build_track_patterns(self) -> None:
        def _process(data: dict) -> tuple[list[tuple[re.Pattern[str], str]], list[tuple[re.Pattern[str], str]], list[dict]]:
            entries = data.get("tracks", [])
            name_patterns = compile_patterns(entries, pattern_key="matcher", name_key="name")
            folder_patterns = compile_patterns(entries, pattern_key="matcher", name_key="lmu_folder")
            return name_patterns, folder_patterns, entries

        self.file_track_name_patterns, self.file_track_folder_patterns, self._track_entries = load_catalog_with_fallback(
            self.mapping_json_path, REMOTE_MAPPINGS_ENABLED, REMOTE_MAPPINGS_URL, REMOTE_MAPPINGS_TIMEOUT, "mapping", _process,
        )
        # Each manual_mapping row's matcher is a single "|"-joined regex string;
        # wrapping it in a one-element list lets compile_patterns() compile it
        # as-is (a "|"-joined pattern matches identically to trying each
        # alternative separately).
        custom_entries = [{"name": m["name"], "matcher": [m["matcher"]]} for m in settings_db.get_manual_mappings("track")]
        self.custom_track_patterns = compile_patterns(custom_entries, pattern_key="matcher", name_key="name")

    def get_track_folder_name(self, track: str) -> str | None:
        # Physical LMU folder identity (lmu_folder) - used to compute the
        # installation path. First-match-wins: file-derived patterns first,
        # then per-user DB customizations, then None (callers fall back to
        # the -HYMO suffix).
        normalized = self._normalize_track(track)
        for pattern, lmu_folder in self.file_track_folder_patterns:
            if pattern.search(normalized):
                return lmu_folder
        for pattern, lmu_folder in self.custom_track_patterns:
            if pattern.search(normalized):
                return lmu_folder
        return None

    def get_official_track_name(self, track: str) -> str | None:
        # Official, app-wide track identity (name) - used to officialize
        # installed_setups.track. Same precedence as get_track_folder_name.
        normalized = self._normalize_track(track)
        for pattern, name in self.file_track_name_patterns:
            if pattern.search(normalized):
                return name
        for pattern, lmu_folder in self.custom_track_patterns:
            # User "Correggi" mappings have no `name` distinct from
            # lmu_folder_name - use that as the official value too.
            if pattern.search(normalized):
                return lmu_folder
        return None

    def get_known_folder_names(self) -> list[str]:
        # Sorted, de-duplicated lmu_folder values, for the GUI's "Correggi" <select>.
        file_names = {t["lmu_folder"] for t in self._track_entries}
        custom_names = {m["name"] for m in settings_db.get_manual_mappings("track")}
        return sorted(file_names | custom_names)

    def add_or_update_mapping(self, track: str, lmu_folder_name: str) -> None:
        settings_db.upsert_manual_mapping("track", lmu_folder_name, track)
        # Also register a self-matching pattern for the folder name itself, so
        # picking lmu_folder_name back out of get_known_folder_names() (e.g.
        # the Upload tab's Track dropdown) resolves to this same existing
        # folder instead of creating a new "<folder> - HYMO" one. Skipped when
        # it's already identical to `track`'s own pattern (nothing to add) or
        # when lmu_folder_name already resolves on its own (a known
        # mapping.json track, most commonly) - otherwise this would pollute
        # that track's matcher with its own name as a spurious extra
        # alternative (e.g. mapping "Nordschleife" onto the existing "Monza"
        # would leave "Monza"'s matcher as "Nordschleife|Monza" instead of
        # just "Nordschleife").
        if track != lmu_folder_name and self.get_track_folder_name(lmu_folder_name) is None:
            settings_db.upsert_manual_mapping("track", lmu_folder_name, lmu_folder_name)

    def refresh(self) -> None:
        # Rebuild from the now-updated file/DB. A plain attribute reassignment: safe
        # under the GIL, no lock needed.
        self.build_track_patterns()
