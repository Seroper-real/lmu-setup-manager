"""Dev utility: deletes sandbox-fixture setups (HYMO and GO alike) from a REAL
Dropbox account.

Undoes two kinds of test uploads onto a real Dropbox share:
  - A MASTER run made with `--mock-tracktitan` against real Dropbox credentials
    (see .vscode/launch.json's "Master - mock TrackTitan + LMU, real Dropbox"
    profile) - a documented way to exercise the real upload path without a
    TrackTitan subscription. That workflow uploads the checked-in sandbox
    catalog's setups exactly like a real run would, tagged with a "SANDBOX"
    marker in the filename (see Setup.remote_filename); this script uses the
    catalog's own ids to know which remote entries are safe to delete.
  - The checked-in GO Setups fixtures (sandbox/dropbox/**/GO-SANDBOX-*.zip)
    copied by hand onto the same real share to test GO installation for real.
    A GO archive has no id, so these are recognized by (car, track) folder +
    the same "SANDBOX" filename marker - see cleanup_sandbox_go_setups().

Requires real Dropbox credentials configured (settings.db or env vars) and
MOCK_DROPBOX left off, same as any real MASTER/SLAVE run.

Usage: python src/cleanup_sandbox_dropbox.py
"""
import logging

from clients.mocks.mock_track_titan_client import MockTrackTitanClient
from clients.protocols import build_dropbox_client
from orchestration.sandbox_cleanup import cleanup_sandbox_go_setups, cleanup_sandbox_setups

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    mock_tracktitan = MockTrackTitanClient()
    dropbox_client = build_dropbox_client()

    deleted_hymo = cleanup_sandbox_setups(dropbox_client, mock_tracktitan.known_setup_ids())
    deleted_go = cleanup_sandbox_go_setups(dropbox_client, mock_tracktitan.known_setup_car_tracks())

    print(f"Deleted {deleted_hymo} sandbox HYMO setup(s) and {deleted_go} sandbox GO archive(s) from Dropbox.")


if __name__ == "__main__":
    main()
