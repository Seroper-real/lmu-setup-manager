import os, logging, threading
from pathlib import Path
from typing import Optional
from clients.protocols import TrackTitanClientProtocol
from core.config import DOWNLOAD_PATH, PAGE_SIZE
from domain.setup import Setup
from domain.setup_db import SetupDb
from clients.track_titan_client import TrackTitanClient

log = logging.getLogger("TrackTitanDownloader")

class DownloadManager:
    def __init__(
        self,
        database : Optional[SetupDb] = None,
        client: Optional[TrackTitanClientProtocol] = None,
        *,
        cancel_event: Optional[threading.Event] = None,
    ):
        if not DOWNLOAD_PATH:
            raise RuntimeError("Missing DOWNLOAD_PATH")
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        # Callers that do not inject a client get the real, token-validating one.
        self.track_titan_client: TrackTitanClientProtocol = client if client is not None else TrackTitanClient()
        self.page = 1
        self.page_size = PAGE_SIZE
        self.finished = False
        self.already_downloaded : set[str] = set()
        self.already_installed : set[str] = set()
        # MASTER mode constructs without a DB; the install-skip check below is
        # guarded so download() simply always fetches when no DB is present.
        self.database : Optional[SetupDb] = database
        # Set by the GUI to stop pagination between pages without killing an
        # in-flight request.
        self.cancel_event: Optional[threading.Event] = cancel_event
        self.get_downloaded_setup_uuid()
    
    def get_downloaded_setup_uuid(self) -> None:
        self.already_downloaded.update({
            f[-40:-4]
            for f in os.listdir(DOWNLOAD_PATH)
            if f.endswith(".zip")
            })
                
    def get_setups_list(self) -> list[Setup]:
        if self.finished: return []
        if self.cancel_event is not None and self.cancel_event.is_set(): return []
        # Throttle *before* the request, never after: the interval is measured from
        # the previous request, so any work the caller did since then already
        # counts and only the remainder is slept.
        self.track_titan_client.throttle()
        res = self.track_titan_client.get(
            "/v2/games/leMansUltimate/setups",
            params={"page": self.page, "limit": self.page_size}
        )
        setups : list[Setup] = [Setup(setup) for setup in res["data"]["setups"]]
        log.debug(f"PAGE {self.page} found:{len(setups)}")
        if len(setups) < self.page_size: self.finished = True
        self.page += 1
        return setups

    def restart_setups_list(self) -> None:
        self.page = 1
        self.finished = False

    def download(self, setup: Setup) -> Path | None:
        if self.database and self.database.is_setup_installed_last_version(setup):
            log.info(f"Setup already installed. Skipping")
            return #Setup già scaricato
        
        path = Path(f"{DOWNLOAD_PATH}/HYMO-{setup.safe_track}-{setup.id}.zip")

        if setup.id not in self.already_downloaded:
            log.debug(f"Downloading setup {setup.id}")
            self.track_titan_client.throttle()
            data = self.track_titan_client.download_link(setup.id)
            download_url = data["url"]
            # Scaricare il file
            file_resp = self.track_titan_client.download(download_url)
            with open(path, "wb") as f:
                f.write(file_resp.content)
            log.info(f"Download completed for {setup.id}")
            self.already_downloaded.add(setup.id)
        else:
            log.debug(f"Setup downloaded but not yet installed for {setup.id}")
        return path
