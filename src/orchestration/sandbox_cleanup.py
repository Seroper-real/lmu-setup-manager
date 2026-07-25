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


def cleanup_sandbox_go_setups(
    dropbox_client: DropboxClientProtocol, expected_car_tracks: set[tuple[str, str]]
) -> int:
    """Delete every GO Setups archive on `dropbox_client` that looks like
    manually-uploaded sandbox test data (see the "Enable manual uploading of
    these setups to the real Dropbox for testing purposes" GO fixtures under
    sandbox/dropbox/**/GO-SANDBOX-*.zip).

    A GO archive has no TrackTitan-style id to match on (see
    domain.go_setup/RemoteGoSetup), so two independent signals are required
    together before deleting one - either alone could plausibly match a real
    user's own GO archive:
      - its (car, track) folder is one of `expected_car_tracks` (the sandbox
        catalog's own safe_car/safe_track pairs - see
        MockTrackTitanClient.known_setup_car_tracks());
      - its filename carries the "SANDBOX" marker.

    A GO archive already missing on Dropbox is logged and skipped, not raised,
    same as cleanup_sandbox_setups().

    Returns the number of archives actually deleted.
    """
    deleted = 0
    for remote in dropbox_client.list_go_setups():
        if (remote.car, remote.track) not in expected_car_tracks:
            continue
        if "sandbox" not in remote.name.lower():
            continue
        if dropbox_client.delete_if_exists(remote.path_lower):
            deleted += 1
    return deleted
