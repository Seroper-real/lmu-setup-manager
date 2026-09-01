from typing import Any, Optional
import re, requests, time, random, logging
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

# The TrackTitan web app's origin, used only for the Origin/Referer headers
# below. The page the GUI's automatic token-fetch flow opens for the user to log
# into is no longer a constant here: it lives in config/mapping.json's "conf"
# section (resolved by processing.catalog_loader.load_tracktitan_login_url), so
# it can be corrected via the remote mirror without an app release.
TRACKTITAN_APP_ORIGIN = "https://app.tracktitan.io"

# requests' default "python-requests/x.x" User-Agent is a well-known automated-
# client fingerprint; TrackTitan's API front end has been seen rejecting it
# outright (417 Expectation Failed) even with otherwise-valid tokens. These
# requests already carry a real, user-owned session's tokens (extracted via the
# readme's bookmarklet) - mirroring the headers the actual app.tracktitan.io
# frontend sends just keeps an already-authorized request from being fingerprinted
# as a generic script.
_BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": TRACKTITAN_APP_ORIGIN,
    "Referer": f"{TRACKTITAN_APP_ORIGIN}/",
}

# Cognito cookie name suffixes, e.g.
# "CognitoIdentityServiceProvider.<clientId>.<username>.accessToken" - the
# client/username segments vary per account, so only the suffix is stable.
# Kept in sync with the readme.md bookmarklet, which reads document.cookie with
# the same three patterns.
_COOKIE_PATTERNS: dict[str, re.Pattern[str]] = {
    "ACCESS_TOKEN_LIST": re.compile(r"\.accessToken$"),
    "ACCESS_TOKEN_DOWNLOAD": re.compile(r"\.idToken$"),
    "USER_ID": re.compile(r"\.LastAuthUser$"),
}


def extract_tokens_from_cookies(cookies: dict[str, str]) -> Optional[dict[str, str]]:
    """Finds the three TrackTitan credential values among a browser's cookies,
    matching names by suffix rather than an exact key. Returns None unless all
    three are present - a partial login (e.g. caught mid-redirect) isn't usable."""
    found: dict[str, str] = {}
    for name, pattern in _COOKIE_PATTERNS.items():
        match = next((value for key, value in cookies.items() if pattern.search(key)), None)
        if match is None:
            return None
        found[name] = match
    return found


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
        headers = {
            **_BROWSER_HEADERS,
            "Authorization": f"{ACCESS_TOKEN_LIST}",
            "Accept": "application/json, text/plain, */*",
            "x-consumer-id": f"{CONSUMER_ID}"
        }
        try:
            r = requests.get(url, params=params, timeout=NETWORK_TIMEOUT, headers=headers)
        finally:
            self._mark_request()
        self._raise_for_status(r)
        return r.json()

    def download_link(self, setup_id: str) -> dict[str, Any]:
        url = f"{BASE_URL}/v1/user/{USER_ID}/setup/{setup_id}/download"
        headers = {
            **_BROWSER_HEADERS,
            "accept": "application/json, text/plain, */*",
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
            response = requests.get(url, timeout=NETWORK_TIMEOUT, headers=_BROWSER_HEADERS)
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
                    "Your access tokens may have expired - update them in Settings.",
                    code="tracktitan",
                    status=response.status_code,
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
