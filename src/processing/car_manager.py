import re
import unicodedata
import logging
from core.config import REMOTE_MAPPINGS_ENABLED, REMOTE_MAPPINGS_TIMEOUT, REMOTE_MAPPINGS_URL
from core.utils import get_path
from processing.catalog_loader import compile_patterns, load_catalog_with_fallback

log = logging.getLogger("TrackTitanDownloader")

class CarManager:
    """Single-layer car matcher: config/mapping.json's "cars" section
    (dev-maintained, pushed to the repo/remote mirror without a release).
    Unlike TrackManager, there is no per-user "Correggi" override layer - not
    requested for cars, and cars have no physical-folder concept to resolve
    separately from their official name."""

    def __init__(self) -> None:
        self.mapping_json_path = get_path("config/mapping.json")
        self.car_patterns: list[tuple[re.Pattern[str], str]] = []
        self.refresh()

    def _normalize_car(self, car: str) -> str:
        return unicodedata.normalize("NFC", car).strip()

    def build_car_patterns(self) -> None:
        self.car_patterns = load_catalog_with_fallback(
            self.mapping_json_path, REMOTE_MAPPINGS_ENABLED, REMOTE_MAPPINGS_URL, REMOTE_MAPPINGS_TIMEOUT, "mapping",
            lambda data: compile_patterns(data.get("cars", []), pattern_key="matcher", name_key="name"),
        )

    def get_car_name(self, car: str) -> str | None:
        normalized = self._normalize_car(car)
        for pattern, name in self.car_patterns:
            if pattern.search(normalized):
                return name
        return None

    def refresh(self) -> None:
        self.build_car_patterns()
