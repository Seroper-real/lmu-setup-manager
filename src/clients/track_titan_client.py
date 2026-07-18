from typing import Any, Optional
import requests, time, random, logging
from core.config import (
    BASE_URL,
    ACCESS_TOKEN_LIST,
    ACCESS_TOKEN_DOWNLOAD,
    CONSUMER_ID,
    MAX_DELAY,
    MIN_DELAY,
    NETWORK_TIMEOUT,
    USER_ID,
)
from core.errors import AuthError

log = logging.getLogger("TrackTitanDownloader")

class TrackTitanClient:
    def __init__(self):
        if not BASE_URL:
            raise RuntimeError("Missing BASE_URL")
        if not ACCESS_TOKEN_LIST:
            raise RuntimeError("Missing ACCESS_TOKEN_LIST")
        if not ACCESS_TOKEN_DOWNLOAD:
            raise RuntimeError("Missing ACCESS_TOKEN_DOWNLOAD")
        if not CONSUMER_ID:
            raise RuntimeError("Missing CONSUMER_ID")
        if not USER_ID:
            raise RuntimeError("Missing USER_ID")
        # Zero means "long ago", so the very first throttle() does not wait.
        self._last_request_at: float = 0.0

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        url = f"{BASE_URL}{path}"
        try:
            r = requests.get(url, params=params, timeout=NETWORK_TIMEOUT, headers={
                "Authorization": f"{ACCESS_TOKEN_LIST}",
                "Accept": "application/json, text/plain, */*",
                "x-consumer-id": f"{CONSUMER_ID}"
            })
        finally:
            self._mark_request()
        self._raise_for_status(r)
        return r.json()

    def download_link(self, setup_id: str) -> dict[str, Any]:
        url = f"{BASE_URL}/v1/user/{USER_ID}/setup/{setup_id}/download"
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
            "authorization": f"{ACCESS_TOKEN_DOWNLOAD}",
            "x-consumer-id": f"{CONSUMER_ID}"
        }
        # POST without body (curl -X POST with content-length: 0)
        try:
            response = requests.post(url, headers=headers, data=None, timeout=NETWORK_TIMEOUT)
        finally:
            self._mark_request()
        self._raise_for_status(response)
        log.debug(response.json())
        return response.json()

    def download(self, url: str) -> requests.Response:
        try:
            response = requests.get(url, timeout=NETWORK_TIMEOUT)
        finally:
            self._mark_request()
        self._raise_for_status(response)
        return response

    def _mark_request(self) -> None:
        self._last_request_at = time.monotonic()

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        """raise_for_status(), but a 401/403 becomes an AuthError - the GUI shows
        those as a dedicated "your tokens expired" popup instead of a generic
        run-failed message."""
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if getattr(response, "status_code", None) in (401, 403):
                raise AuthError(
                    f"TrackTitan authentication failed (HTTP {response.status_code}). "
                    "Your access tokens may have expired - update them in Settings."
                ) from e
            raise

    def _target_interval(self) -> float:
        """A Gaussian-distributed interval, clamped to the configured window."""
        avg: float = (MIN_DELAY + MAX_DELAY) / 2
        jitter: float = (MAX_DELAY - MIN_DELAY) / 4  # ~2 sigma spans the window
        return min(MAX_DELAY, max(MIN_DELAY, random.gauss(avg, jitter)))

    def throttle(self) -> None:
        """Space requests out to look human, without wasting time.

        This is a *minimum interval* since the last request, not an unconditional
        sleep: whatever the caller did in the meantime (extracting, zipping,
        uploading to Dropbox) already spaced the requests apart, so only the
        remainder is slept. MASTER therefore pays no more than FULL does.
        """
        remaining: float = self._target_interval() - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)
