class AuthError(Exception):
    """Raised when an external system (TrackTitan, Dropbox) rejects our
    credentials - expired or invalid tokens, not a transient network failure.

    Lives in its own dependency-free module so gui.api can catch it without
    importing the concrete clients (clients.protocols builds those lazily, per
    the active sandbox flags - see build_track_titan_client()/build_dropbox_client())."""
