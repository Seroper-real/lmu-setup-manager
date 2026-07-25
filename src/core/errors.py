class AuthError(Exception):
    """Raised when an external system (TrackTitan, Dropbox) rejects our
    credentials - expired or invalid tokens, not a transient network failure.

    Lives in its own dependency-free module so gui.api can catch it without
    importing the concrete clients (clients.protocols builds those lazily, per
    the active sandbox flags - see build_track_titan_client()/build_dropbox_client()).

    `message` is English and only ever reaches the log file - the GUI never
    displays str(exc) directly. It instead renders a localized string keyed
    off `code` ("tracktitan" / "dropbox" / "dropbox_scope"), so this error
    shows in the user's active app language instead of always in English.
    `status` carries the HTTP status for the TrackTitan case, where the
    localized message interpolates it."""

    def __init__(self, message: str, code: str = "generic", status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
