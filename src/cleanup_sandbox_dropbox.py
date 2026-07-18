"""Dev utility: deletes sandbox-fixture setups from a REAL Dropbox account.

Undoes a MASTER run made with `--mock-tracktitan` against real Dropbox
credentials (see .vscode/launch.json's "Master - mock TrackTitan + LMU, real
Dropbox" profile) - a documented way to exercise the real upload path without a
TrackTitan subscription. That workflow uploads the checked-in sandbox catalog's
setups to the shared Dropbox folder exactly like a real run would; this script
tears that test data back out, using the same catalog to know which remote ids
are safe to delete.

Requires real Dropbox credentials configured (settings.db or env vars) and
MOCK_DROPBOX left off, same as any real MASTER/SLAVE run.

Usage: python src/cleanup_sandbox_dropbox.py
"""
import logging

from clients.mocks.mock_track_titan_client import MockTrackTitanClient
from clients.protocols import build_dropbox_client
from orchestration.sandbox_cleanup import cleanup_sandbox_setups

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    sandbox_ids = MockTrackTitanClient().known_setup_ids()
    deleted = cleanup_sandbox_setups(build_dropbox_client(), sandbox_ids)
    print(f"Deleted {deleted} sandbox setup(s) from Dropbox.")


if __name__ == "__main__":
    main()
