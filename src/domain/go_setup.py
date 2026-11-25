import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# "GO V1.4.3 9X8EVO HYP MON Q Safe.svm" -> (1, 4, 3). Numeric tuple so that
# V1.10.0 correctly outranks V1.4.3 (a string compare would not). HYMO files carry
# the version after the brand instead: "HYMO 1.3.3 TR010 IMO CQ.svm" -> (1, 3, 3).
_GO_VERSION_RE: re.Pattern[str] = re.compile(
    r"(?<![A-Za-z0-9])(?:V|HYMO\s+)(\d+(?:\.\d+)*)(?![A-Za-z0-9])", re.IGNORECASE,
)


def parse_go_version(file_name: str) -> Optional[tuple[int, ...]]:
    """Extract the version token (GO "Vx.y.z" or HYMO "HYMO x.y.z") from a setup file name, or None if absent."""
    match = _GO_VERSION_RE.search(file_name)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _pad(version: tuple[int, ...], length: int) -> tuple[int, ...]:
    return version + (0,) * (length - len(version))


def filter_latest_go_version(files: list[Path]) -> list[Path]:
    """Keep only the files carrying the globally highest version found among
    `files` (older-version files are dropped even for variants that exist only
    in older versions). Files with no parseable version are always kept; if no
    file has a version, the list is returned unchanged."""
    versions: dict[Path, tuple[int, ...]] = {}
    for file in files:
        version = parse_go_version(file.name)
        if version is not None:
            versions[file] = version
    if not versions:
        return list(files)
    width: int = max(len(v) for v in versions.values())
    highest: tuple[int, ...] = max(_pad(v, width) for v in versions.values())
    return [f for f in files if f not in versions or _pad(versions[f], width) == highest]


def version_key(file_name: str) -> Optional[tuple[str, tuple[int, ...]]]:
    """Split a setup file name into (identity key, version). The key is the name
    with the version token removed and whitespace/case normalized, so
    "HYMO 1.2.4 BMWHY PR CQ.svm" and "HYMO 1.4.3 BMWHY PR CQ.svm" share a key
    while a different layout ("... PR1A-V2 CQ.svm") does not. None when the
    name carries no version."""
    match = _GO_VERSION_RE.search(file_name)
    if match is None:
        return None
    stripped: str = file_name[: match.start()] + " " + file_name[match.end():]
    key: str = " ".join(stripped.lower().split())
    return key, tuple(int(part) for part in match.group(1).split("."))


def compare_versions(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    """-1 / 0 / 1, comparing numerically with zero padding (1.4 == 1.4.0)."""
    width: int = max(len(a), len(b))
    pa, pb = _pad(a, width), _pad(b, width)
    return (pa > pb) - (pa < pb)


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
