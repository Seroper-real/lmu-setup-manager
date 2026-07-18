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
    def __init__(self,data: dict):
        self.data = data
        self._safe_track = self.track.replace("/", "_").replace("\\", "_").replace("-", "_")

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
    def car(self) -> str:
        return self.combo["car"]["name"]
    
    @property
    def track(self) -> str:
        return self.combo["track"]["name"]
    
    @property
    def safe_track(self) -> str:
        return self._safe_track

    @safe_track.setter
    def safe_track(self,value: str) -> None:
        self._safe_track = value

    @property
    def safe_car(self) -> str:
        # Same sanitization as safe_track, plus spaces (e.g. "Ferrari 499P").
        return self.car.replace("/", "_").replace("\\", "_").replace("-", "_").replace(" ", "_")

    @property
    def remote_filename(self) -> str:
        # Filesystem/URL-friendly name used on the Dropbox share. Spaces in the
        # track are collapsed too so the final name has no spaces. The HYMO-
        # prefix brands the file as published by this tool (see _REMOTE_NAME_RE).
        track = self.safe_track.replace(" ", "_")
        return f"HYMO-{track}_{self.safe_car}_{self.id}_{self.last_updated}.zip"

    @property
    def remote_relative_path(self) -> str:
        # Where the package actually lands on the share: one subfolder per car,
        # so a human browsing Dropbox can find setups by car without a DB.
        return f"{self.safe_car}/{self.remote_filename}"

    @property
    def hotlap_link(self) -> Optional[str]:
        return self.data["hotlapLink"]
    
    @property
    def last_updated(self) -> int:
        return self.data["lastUpdatedAt"]
    
    @property
    def is_bundle(self) -> bool:
        return self.data["isBundle"]