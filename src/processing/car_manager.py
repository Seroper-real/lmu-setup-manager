import re
import unicodedata
import logging
from typing import Optional
from core.config import REMOTE_MAPPINGS_ENABLED, REMOTE_MAPPINGS_TIMEOUT, REMOTE_MAPPINGS_URL
from core.utils import get_path
from core import settings_db
from processing.catalog_loader import compile_patterns, extract_value_map, load_catalog_with_fallback

log = logging.getLogger("TrackTitanDownloader")

class CarManager:
    """Two-layer car matcher: config/mapping.json's "cars" section
    (dev-maintained, pushed to the repo/remote mirror without a release)
    first, then settings.db's manual_mapping per-user customizations
    (type="car"), same fallback layer TrackManager has always had for
    tracks. A None result means the setup is skipped entirely by callers
    (see SetupManager.install_setup, MasterManager, SlaveManager)."""

    # mapping.json's raw "class" values -> the class-logo asset name
    # (assets/class-logos/<LABEL>.png). "lmp2 (elms)" is a distinct raw value
    # from "lmp2" but shares the same P2 logo.
    _CLASS_LABELS: dict[str, str] = {
        "hypercar": "HYPERCAR",
        "lmgt3": "GT3",
        "lmgte": "GTE",
        "lmp2": "P2",
        "lmp2 (elms)": "P2",
        "lmp3": "P3",
    }

    def __init__(self) -> None:
        self.mapping_json_path = get_path("config/mapping.json")
        self.car_patterns: list[tuple[re.Pattern[str], str]] = []
        self.custom_car_patterns: list[tuple[re.Pattern[str], str]] = []
        self.car_classes: dict[str, str] = {}
        self._car_entries: list[dict] = []
        self.refresh()

    def _normalize_car(self, car: str) -> str:
        return unicodedata.normalize("NFC", car).strip()

    def _normalize_class(self, raw_class: str) -> Optional[str]:
        return self._CLASS_LABELS.get(raw_class.strip().lower())

    def build_car_patterns(self) -> None:
        def _process(data: dict) -> tuple[list[tuple[re.Pattern[str], str]], dict[str, str], list[dict]]:
            entries = data.get("cars", [])
            patterns = compile_patterns(entries, pattern_key="matcher", name_key="name")
            raw_classes = extract_value_map(entries, name_key="name", value_key="class")
            return patterns, raw_classes, entries

        self.car_patterns, raw_classes, self._car_entries = load_catalog_with_fallback(
            self.mapping_json_path, REMOTE_MAPPINGS_ENABLED, REMOTE_MAPPINGS_URL, REMOTE_MAPPINGS_TIMEOUT, "mapping", _process,
        )
        self.car_classes = {
            name: normalized
            for name, raw in raw_classes.items()
            if (normalized := self._normalize_class(raw)) is not None
        }
        # Same "|"-joined-single-regex shape as TrackManager.custom_track_patterns.
        custom_entries = [{"name": m["name"], "matcher": [m["matcher"]]} for m in settings_db.get_manual_mappings("car")]
        self.custom_car_patterns = compile_patterns(custom_entries, pattern_key="matcher", name_key="name")

    def get_car_name(self, car: str) -> str | None:
        normalized = self._normalize_car(car)
        for pattern, name in self.car_patterns:
            if pattern.search(normalized):
                return name
        for pattern, name in self.custom_car_patterns:
            if pattern.search(normalized):
                return name
        return None

    def get_car_class(self, name: str) -> Optional[str]:
        return self.car_classes.get(name)

    def get_all_cars(self) -> list[dict[str, object]]:
        """Every car mapping.json declares, in its own order - for the Upload
        tab's car dropdown."""
        return [
            {"name": entry["name"], "carClass": self.car_classes.get(entry["name"])}
            for entry in self._car_entries
        ]

    def add_or_update_mapping(self, car: str, name: str) -> None:
        settings_db.upsert_manual_mapping("car", name, car)
        # Same self-matching safeguard TrackManager.add_or_update_mapping
        # uses: picking `name` back out of get_all_cars() (e.g. the Upload
        # tab's Car dropdown) must resolve to itself, not stay unmatched.
        # Skipped when `name` already resolves on its own (a known
        # mapping.json car, most commonly) - otherwise this would pollute
        # that car's matcher with its own name as a spurious extra
        # alternative (see TrackManager.add_or_update_mapping for the
        # "Nordschleife"/"Monza" example this mirrors).
        if car != name and self.get_car_name(name) is None:
            settings_db.upsert_manual_mapping("car", name, name)

    def refresh(self) -> None:
        self.build_car_patterns()
