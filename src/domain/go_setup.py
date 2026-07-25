from dataclasses import dataclass
from typing import Optional


def looks_like_go_name(name: str) -> bool:
    """Cheap prefix check: is this even worth considering as a GO Setups candidate?"""
    return name.lower().startswith("go")


def is_go_zip_name(name: str) -> bool:
    return looks_like_go_name(name) and name.lower().endswith(".zip")


@dataclass
class RemoteGoSetup:
    """One conforming GO Setups zip on the remote share, found under a car/track
    folder. No setup_id here: GO archives have no TrackTitan-style stable id, so
    identity is resolved per run from the DB (see SlaveManager._process_go)."""
    name: str
    path_lower: str
    car: str
    track: str


def parse_go_entry(name: str, path_lower: str, relative_segments: list[str]) -> Optional[RemoteGoSetup]:
    """Validate a share entry as a GO Setups archive: must sit exactly 3 segments
    deep (<Car>/<Track>/<file.zip>) and have a GO-prefixed zip name."""
    if len(relative_segments) != 3 or not is_go_zip_name(name):
        return None
    car, track, _ = relative_segments
    return RemoteGoSetup(name=name, path_lower=path_lower, car=car, track=track)
