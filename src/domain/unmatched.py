import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UnmatchedSetup:
    """One setup skipped during a run because its car or track (or both)
    didn't resolve against mapping.json + the manual_mapping fallback.
    `track`/`car` are the raw, unresolved text as seen from `source` - never
    an officialized name, since there is none. `track_matched`/`car_matched`
    record which of the two actually failed to resolve (a setup can be
    skipped with only one side unmatched) - the GUI's correction dialog uses
    these to only ask for, and only persist, the side that's actually wrong."""
    track: str
    car: str
    source: str  # "tracktitan" | "dropbox"
    track_matched: bool
    car_matched: bool


class UnmatchedTracker:
    """Collects UnmatchedSetup entries over the course of one run, so the GUI
    can show a single end-of-run correction dialog instead of installing/
    publishing them under a placeholder name. Thread-safe: MasterManager's
    producer thread and (defensively) any future concurrent caller may both
    record into the same instance."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: set[tuple[str, str, str]] = set()
        self._items: list[UnmatchedSetup] = []

    def record(self, track: str, car: str, source: str, *, track_matched: bool, car_matched: bool) -> None:
        key = (source, track, car)
        with self._lock:
            if key in self._seen:
                return
            self._seen.add(key)
            self._items.append(UnmatchedSetup(
                track=track, car=car, source=source, track_matched=track_matched, car_matched=car_matched,
            ))

    def serialize(self) -> Optional[list[dict[str, object]]]:
        """JSON-ready payload for ProgressEvent.unmatched - None when empty,
        so callers/the GUI never need to special-case an empty list."""
        with self._lock:
            if not self._items:
                return None
            return [
                {
                    "track": u.track, "car": u.car, "source": u.source,
                    "trackMatched": u.track_matched, "carMatched": u.car_matched,
                }
                for u in self._items
            ]
