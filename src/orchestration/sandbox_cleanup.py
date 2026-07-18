import logging

from clients.protocols import DropboxClientProtocol

log = logging.getLogger("TrackTitanDownloader")


def cleanup_sandbox_setups(dropbox_client: DropboxClientProtocol, sandbox_setup_ids: set[str]) -> int:
    """Delete every remote setup on `dropbox_client` whose id is in
    `sandbox_setup_ids`. Meant to undo a MASTER run made with `--mock-tracktitan`
    against a *real* Dropbox account (see .vscode/launch.json's "Master - mock
    TrackTitan + LMU, real Dropbox" profile, a documented way to exercise the
    real upload path without a TrackTitan subscription): that workflow uploads
    the checked-in sandbox catalog's setups to the shared folder exactly like a
    real run would, so the catalog's own ids are what identify which remote
    entries are test data safe to delete.

    A setup already missing on Dropbox (deleted by hand, or by a previous run of
    this same cleanup) is logged and skipped, not raised - one missing entry
    must not abort the rest of the cleanup.

    Returns the number of setups actually deleted.
    """
    deleted = 0
    for remote in dropbox_client.list_setups():
        if remote.setup_id not in sandbox_setup_ids:
            continue
        if dropbox_client.delete_if_exists(remote.path_lower):
            deleted += 1
    return deleted
