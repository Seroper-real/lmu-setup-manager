import re
from dataclasses import dataclass
from typing import Optional

# Share filename scheme: HYMO-{track}_{car}_{id}_{last_update_ts}.zip
# The HYMO- prefix brands files this tool published, so SLAVE (and MASTER's own
# reconciliation) ignore anything else a human may have dropped on the share.
# The id is a UUID (hyphens, never underscores) and ts is digits, so a
# right-anchored match recovers them even when the sanitized track/car
# segments themselves contain underscores.
_REMOTE_NAME_RE = re.compile(r"^HYMO-.+_(?P<id>[^_]+)_(?P<ts>\d+)\.zip$", re.IGNORECASE)


def parse_remote_zip_name(name: str) -> Optional[tuple[str, int]]:
    """Parse a share zip filename into (setup_id, last_update_ts), or None."""
    match = _REMOTE_NAME_RE.match(name)
    if not match:
        return None
    return match.group("id"), int(match.group("ts"))


def sanitize_identity(value: str) -> str:
    """Strip the real path-breaking characters (spaces are left alone). Shared
    by Setup.safe_car/safe_track (Dropbox folder naming) and by SetupDb, which
    applies it to every car/track written to installed_setups so a HYMO row's
    raw TrackTitan name and a GO row's Dropbox-folder-derived name always
    match for the same real car/track."""
    return value.replace("/", "_").replace("\\", "_").replace("-", "_")


@dataclass
class RemoteSetup:
    """One conforming setup zip on the remote share.

    Lives here rather than in dropbox_client so that backends which do not use
    the Dropbox SDK can produce it without importing that SDK.
    """
    name: str
    path_lower: str
    setup_id: str
    ts: int


class Setup:
    def __init__(self, data: dict, sandbox: bool = False):
        self.data = data
        # Set when built from the mock TrackTitan catalog (MOCK_TRACKTITAN) -
        # see remote_filename. Never true for a real TrackTitan setup, so real
        # uploads are byte-for-byte unaffected.
        self.sandbox = sandbox
        # Computed lazily (see safe_track/safe_car below): some catalog entries
        # (e.g. bundles) have no track/car in their combo at all, and callers
        # are expected to check is_bundle before ever reading these.
        self._safe_track: Optional[str] = None
        self._safe_car: Optional[str] = None

    @property
    def id(self) -> str:
        return self.data["id"]
    
    @property
    def title(self) -> str:
        return self.data["title"]
    
    @property
    def combo(self) -> dict:
        return self.data["setupCombos"][0]
    
    @property
    def car(self) -> Optional[str]:
        # Some catalog entries (e.g. certain e-sports/event setups) omit the
        # car from their combo entirely - None here, rather than a KeyError,
        # is what lets callers fold this into their existing "not matched"
        # skip path instead of crashing.
        car = self.combo.get("car")
        return car["name"] if car else None

    @property
    def track(self) -> Optional[str]:
        track = self.combo.get("track")
        return track["name"] if track else None
    
    @property
    def safe_track(self) -> str:
        if self._safe_track is None:
            self._safe_track = sanitize_identity(self.track)
        return self._safe_track

    @safe_track.setter
    def safe_track(self,value: str) -> None:
        self._safe_track = value

    @property
    def safe_car(self) -> str:
        # Same sanitization as safe_track by default (only the real
        # path-breaking characters are replaced, spaces are left alone),
        # overridable via the setter once CarManager resolves an official
        # catalog name for this car. Shared by the Dropbox folder path
        # (remote_relative_path) and, after local space-collapsing below, the
        # zip filename - GO Setups read their car identity straight back out
        # of this same folder name, so keeping it space-preserving is what
        # makes a GO archive's car match TrackTitan's.
        if self._safe_car is None:
            self._safe_car = sanitize_identity(self.car)
        return self._safe_car

    @safe_car.setter
    def safe_car(self, value: str) -> None:
        self._safe_car = value

    def _branded_filename(self, brand: str) -> str:
        # Filesystem/URL-friendly name used on the Dropbox share. Spaces in the
        # track and car are collapsed too so the final name has no spaces.
        track = self.safe_track.replace(" ", "_")
        car = self.safe_car.replace(" ", "_")
        return f"{brand}{track}_{car}_{self.id}_{self.last_updated}.zip"

    @property
    def remote_filename(self) -> str:
        # The HYMO- prefix brands the file as published by this tool (see
        # _REMOTE_NAME_RE). A sandbox setup additionally carries a SANDBOX
        # marker right after the brand prefix, so test data uploaded to a real
        # Dropbox account (e.g. via --mock-tracktitan) is instantly
        # recognizable next to real setups and can be found/deleted by
        # cleanup_sandbox_dropbox.py. _REMOTE_NAME_RE still matches: it only
        # anchors on the trailing "_id_ts.zip", not on what comes right after
        # "HYMO-".
        brand = "HYMO-SANDBOX_" if self.sandbox else "HYMO-"
        return self._branded_filename(brand)

    @property
    def go_filename(self) -> str:
        # Same <track>_<car>_<id>_<last_updated>.zip scheme as remote_filename
        # (so a manually-uploaded GO Setups archive carries the same
        # id/date info a HYMO one does), but GO- branded so
        # is_go_zip_name/parse_go_entry (domain/go_setup.py) still recognize
        # it as a GO Setups archive when found on the share.
        return self._branded_filename("GO-")

    @property
    def remote_relative_path(self) -> str:
        # Where the package actually lands on the share: car, then track, so a
        # human browsing Dropbox finds a given car+track's setups - both this
        # tool's own and any manually-uploaded GO Setups archives - in one place.
        return f"{self.safe_car}/{self.safe_track}/{self.remote_filename}"

    @property
    def hotlap_link(self) -> Optional[str]:
        return self.data["hotlapLink"]
    
    @property
    def last_updated(self) -> int:
        return self.data["lastUpdatedAt"]
    
    @property
    def is_bundle(self) -> bool:
        return self.data["isBundle"]