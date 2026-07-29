from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class ProgressKind(str, Enum):
    START = "start"
    INSTALL = "install"
    FINISH = "finish"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True)
class ProgressEvent:
    kind: ProgressKind
    title: str
    meta: Optional[str] = None
    # Set on ERROR events raised from an AuthError (expired/invalid TrackTitan or
    # Dropbox credentials): the GUI shows these as a dedicated popup with a link
    # to Settings instead of folding them into the plain activity log.
    is_auth_error: bool = False
    # AuthError.code/status (see core.errors) - lets the GUI render a localized
    # message instead of the English `title` used for the plain activity log.
    error_code: Optional[str] = None
    error_status: Optional[int] = None
    # Only set on a FINISH/STOPPED event: the distinct track/car strings that
    # didn't resolve against mapping.json + the manual_mapping fallback this
    # run (see domain.unmatched.UnmatchedTracker.serialize), for the GUI's
    # end-of-run correction dialog. None when nothing was skipped.
    unmatched: Optional[dict[str, list[str]]] = None


ProgressCallback = Callable[[ProgressEvent], None]
