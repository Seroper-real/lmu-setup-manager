import threading
from typing import Optional


class UnmatchedTracker:
    """Collects the raw track/car strings that failed to resolve against
    mapping.json + the manual_mapping fallback over the course of one run, so
    the GUI can show a single end-of-run correction dialog. Deduped by value,
    not by setup: hundreds of setups can share the same unmatched track or
    car, and all of them are fixed by a single mapping, so the dialog only
    ever needs to ask about each distinct track/car once. Thread-safe:
    MasterManager's/SlaveManager's producer thread and (defensively) any
    future concurrent caller may both record into the same instance."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # dict, not set: iteration order must follow first-seen order, and a
        # plain dict (values unused) is the simplest ordered-set available.
        self._tracks: dict[str, None] = {}
        self._cars: dict[str, None] = {}

    def record(self, track: str, car: str, *, track_matched: bool, car_matched: bool) -> None:
        with self._lock:
            if not track_matched:
                self._tracks.setdefault(track, None)
            if not car_matched:
                self._cars.setdefault(car, None)

    def serialize(self) -> Optional[dict[str, list[str]]]:
        """JSON-ready payload for ProgressEvent.unmatched - None when empty,
        so callers/the GUI never need to special-case an empty list."""
        with self._lock:
            if not self._tracks and not self._cars:
                return None
            return {"tracks": list(self._tracks), "cars": list(self._cars)}
