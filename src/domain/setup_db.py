from dataclasses import dataclass
import json
import logging
from pathlib import Path
import sqlite3
import time
from core.config import DB_PATH
from domain import migrations
from domain.setup import Setup

log = logging.getLogger("TrackTitanDownloader")

@dataclass
class InstalledSetup:
    setup_id: str
    track: str
    car: str
    install_date: int
    setup_last_update: int
    hotlap_link: str
    api_data: dict
    file_names: list[str]
    track_found: bool
    installation_base_path: str | None
    installation_folder: str | None
    matched_track_id: str | None
    sha256: str | None
    setup_type: str

    @staticmethod
    def from_row(row: tuple) -> "InstalledSetup":
        return InstalledSetup(
            setup_id=row[0],
            track=row[1],
            car=row[2],
            install_date=row[3],
            setup_last_update=row[4],
            hotlap_link=row[5],
            api_data=json.loads(row[6]) if row[6] else {},
            file_names=json.loads(row[7]) if row[7] else [],
            track_found=bool(row[8]),
            installation_base_path=row[9],
            installation_folder=row[10],
            matched_track_id=row[11],
            sha256=row[12],
            setup_type=row[13],
        )
    
class SetupDb:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.create_tables()


    def create_tables(self):
        # Schema creation/upgrades live in domain.migrations, versioned against
        # domain.migrations.SCHEMA_TARGET_VERSION and tracked in the DB's own
        # schema_version table - see that package for the migration history.
        migrations.run_migrations(self.conn)


    def is_installed_last_version(self, setup_id: str, last_updated: int) -> bool:
        cursor = self.conn.execute("SELECT 1 FROM installed_setups WHERE setup_id = ? and setup_last_update >= ?", (setup_id, last_updated))
        try:
            return cursor.fetchone() is not None
        finally:
            cursor.close

    def is_setup_installed_last_version(self, setup: Setup) -> bool:
        return self.is_installed_last_version(setup.id, setup.last_updated)


    def add_installed_setup(
        self,
        setup: Setup,
        file_names: list[Path],
        track_found: bool,
        installation_dir: Path,
        matched_track_id: str | None = None,
        setup_type: str = "HYMO",
        sha256: str | None = None,
    ) -> None:
        with self.conn:
            query = """
                    INSERT INTO installed_setups (setup_id, track, car, install_date, setup_last_update, hotlap_link, api_data, file_names, track_found, installation_base_path, installation_folder, matched_track_id, sha256, setup_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(setup_id) DO UPDATE SET
                        track = excluded.track,
                        car = excluded.car,
                        install_date = excluded.install_date,
                        setup_last_update = excluded.setup_last_update,
                        hotlap_link = excluded.hotlap_link,
                        api_data = excluded.api_data,
                        file_names = excluded.file_names,
                        track_found = excluded.track_found,
                        installation_base_path = excluded.installation_base_path,
                        installation_folder = excluded.installation_folder,
                        matched_track_id = excluded.matched_track_id,
                        sha256 = excluded.sha256,
                        setup_type = excluded.setup_type
                    """
            self.conn.execute(query, (
                setup.id, setup.safe_track, setup.safe_car, int(time.time()*1000), setup.last_updated,
                setup.hotlap_link, json.dumps(setup.data), json.dumps([file.name for file in file_names]),
                int(track_found), str(installation_dir.parent), installation_dir.name, matched_track_id,
                sha256, setup_type
            ))

    def update_installed_setup(self, setup: InstalledSetup) -> None:
        # setup.track/.car are already resolved/official by the time a row
        # reaches this path (set once by add_installed_setup via
        # Setup.safe_track/safe_car) - persisted as-is, never re-sanitized:
        # re-running sanitize_identity here would silently mangle an official
        # name containing a hyphen (e.g. "Cadillac V-Series.R") on every
        # relocate cycle (see SetupManager._try_relocate_setup).
        with self.conn:
            query = """
                    UPDATE installed_setups SET
                        track = ?,
                        car = ?,
                        install_date = ?,
                        setup_last_update = ?,
                        hotlap_link = ?,
                        api_data = ?,
                        file_names = ?,
                        track_found = ?,
                        installation_base_path = ?,
                        installation_folder = ?,
                        matched_track_id = ?,
                        sha256 = ?,
                        setup_type = ?
                    WHERE setup_id = ?
                    """
            self.conn.execute(query, (
                setup.track, setup.car, setup.install_date, setup.setup_last_update,
                setup.hotlap_link, json.dumps(setup.api_data), json.dumps(setup.file_names),
                int(setup.track_found), setup.installation_base_path, setup.installation_folder,
                setup.matched_track_id, setup.sha256, setup.setup_type, setup.setup_id
            ))

    def fetch_setup_files(self,setup_id: str) -> list[str]:
        cursor = self.conn.cursor()
        query = "SELECT file_names FROM installed_setups WHERE setup_id = ?"
        try:
            cursor.execute(query,(setup_id,))
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
            return []
        except Exception as e:
            log.error(f"Error fetching files for {setup_id}: {e}")
            return []
        finally:
            cursor.close()


    def is_track_found(self, setup_id: str) -> bool:
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT track_found FROM installed_setups WHERE setup_id = ?", (setup_id,))
            row = cursor.fetchone()
            if row is None:
                return False
            return bool(row[0])
        except Exception as e:
            log.error(f"Error fetching track_found for {setup_id}: {e}")
            return False
        finally:
            cursor.close()

    def fetch_tracks_not_found(self) -> list[InstalledSetup]:
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT * FROM installed_setups WHERE track_found = 0") #OR track_found IS NULL (for now not consider null values, because are probably pre-migration values)
            return [InstalledSetup.from_row(row) for row in cursor.fetchall()]
        except Exception as e:
            log.error(f"Error fetching unresolved tracks: {e}")
            return []
        finally:
            cursor.close()

    def fetch_all_installed_setups(self) -> list[InstalledSetup]:
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT * FROM installed_setups ORDER BY track, car")
            return [InstalledSetup.from_row(row) for row in cursor.fetchall()]
        except Exception as e:
            log.error(f"Error fetching installed setups: {e}")
            return []
        finally:
            cursor.close()

    def fetch_installed_setup(self, setup_id: str) -> InstalledSetup | None:
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT * FROM installed_setups WHERE setup_id = ?", (setup_id,))
            row = cursor.fetchone()
            return InstalledSetup.from_row(row) if row else None
        except Exception as e:
            log.error(f"Error fetching installed setup {setup_id}: {e}")
            return None
        finally:
            cursor.close()

    def fetch_installed_go_setup(self, car: str, track: str) -> InstalledSetup | None:
        """Look up a GO Setups archive's previously-installed row by its stable
        <Car>/<Track> folder identity, regardless of the zip's current filename
        or content hash. Scoped to setup_type = 'GO': a TrackTitan (HYMO) row
        can legitimately share the same car+track, and must never be matched
        here - reusing its real TrackTitan id as a GO setup_id would corrupt
        it. Relies on there being at most one live GO row per car+track,
        guaranteed because every write for that folder goes through the same
        looked-up setup_id via ON CONFLICT above."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM installed_setups WHERE car = ? AND track = ? AND setup_type = 'GO'",
                (car, track),
            )
            row = cursor.fetchone()
            return InstalledSetup.from_row(row) if row else None
        except Exception as e:
            log.error(f"Error fetching installed GO setup for {car}/{track}: {e}")
            return None
        finally:
            cursor.close()

    def has_installed_hymo_setup(self, car: str, track: str) -> bool:
        """Whether a TrackTitan (HYMO) setup is installed for this exact
        car+track pair - the gate SlaveManager._process_go uses before
        installing a manually-uploaded GO archive for that same folder (a GO
        archive is only trusted once the matching HYMO folder is known-real,
        since that's the only way it could exist per the documented workflow)."""
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "SELECT 1 FROM installed_setups WHERE car = ? AND track = ? AND setup_type = 'HYMO' LIMIT 1",
                (car, track),
            )
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    def delete_installed_setup(self, setup_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM installed_setups WHERE setup_id = ?", (setup_id,))