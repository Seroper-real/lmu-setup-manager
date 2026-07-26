import importlib
import json
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

import webview

from core.progress import ProgressEvent, ProgressKind

if TYPE_CHECKING:
    from domain.setup_db import InstalledSetup

log = logging.getLogger("TrackTitanDownloader")

# Modules that bind GUI-editable config values at import time via `from
# core.config import X` (network delays/timeout/page size, LMU path,
# overwrite/cleanup flags, remote-mappings settings, Dropbox folder/timeout/
# workers, credentials). Reloading core.config alone would not refresh these -
# Python freezes a `from X import Y` binding at the importing module's own
# first import, and these modules are cached in sys.modules for the life of
# the process (each Start Download click only re-instantiates their classes,
# it never re-imports the module). Reloading them here, right after
# core.config, re-executes their top level against the now-current config.
_HOT_RELOAD_MODULES: tuple[str, ...] = (
    "clients.track_titan_client",
    "clients.dropbox_client",
    "orchestration.download_manager",
    "orchestration.master_manager",
    "orchestration.slave_manager",
    "processing.setup_manager",
    "processing.track_manager",
    "processing.car_manager",
)


class Api:
    """The js_api object exposed to the pywebview window.

    Mostly stateless: SetupDb and settings.db (SQLite) remain the sources of truth,
    not fields here. The only state kept on the instance is the
    in-flight download bookkeeping (cancel event/thread), the window reference
    (bound after webview.create_window() returns) and the in-memory mode selection,
    which must win over a possibly-stale core.config.MODE until the next relaunch.
    """

    def __init__(self) -> None:
        # Leading underscore is required, not stylistic: pywebview's own JS-API
        # introspection (webview.util.get_functions) walks every non-underscore
        # attribute of this instance to build window.pywebview.api. A public
        # `window` attribute gets walked straight into the live pywebview
        # Window -> its native WinForms Form -> the .NET accessibility object
        # graph, which pythonnet re-wraps on every access (defeating that
        # walk's id()-based cycle guard) and recurses until Python's recursion
        # limit aborts it (surfaced as "[pywebview] Error while processing
        # window.native.AccessibilityObject.Bounds...RecursionError").
        self._window: Optional[webview.Window] = None
        self._mode_override: Optional[str] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._cancel_event: Optional[threading.Event] = None
        self._running: bool = False
        self._last_error: Optional[str] = None
        # State for the TrackTitan automatic token-fetch flow (a second pywebview
        # window + cookie polling) - separate from the download bookkeeping above
        # since the two can't run concurrently but aren't the same operation.
        self._tt_lock = threading.Lock()
        self._tt_window: Optional[webview.Window] = None
        self._tt_thread: Optional[threading.Thread] = None
        self._tt_cancel_event: Optional[threading.Event] = None
        # Mirrors the frontend's Settings-form dirty state (see app.js's
        # pushSettingsDirty()) - there is no manual Save button anymore, so
        # this is what the native window-close handler below checks before
        # letting the app quit with unsaved edits.
        self._settings_dirty: bool = False

    # ----- mode -----------------------------------------------------------

    def current_mode(self) -> str:
        if self._mode_override is not None:
            return self._mode_override
        from core.config import MODE
        return MODE

    def set_mode(self, mode: str) -> None:
        from core.config import save_config
        self._mode_override = mode
        save_config({"mode": mode})

    # ----- bootstrap --------------------------------------------------------

    def get_bootstrap(self) -> dict[str, object]:
        # Everything the sidebar/mode-badge/Download tab need on first paint, plus a
        # full settings snapshot so the Settings tab can prefill without a second
        # dedicated endpoint (env values included: the mock's "show/hide secrets"
        # toggle only hides them visually, it does not imply they are withheld).
        import core.config as config
        from core.version import APP_VERSION

        available, count = self._installed_summary()
        return {
            "mode": self.current_mode(),
            "appVersion": APP_VERSION,
            "mockTrackTitan": config.MOCK_TRACKTITAN,
            "mockLmu": config.MOCK_LMU,
            "mockDropbox": config.MOCK_DROPBOX,
            "sandboxActive": config.MOCK_TRACKTITAN or config.MOCK_LMU or config.MOCK_DROPBOX,
            "lmuPath": str(config.LMU_SETUPS_BASE_PATH),
            "lmuPathExists": Path(config.LMU_SETUPS_BASE_PATH).exists(),
            "installedAvailable": available,
            "installedCount": count,
            "language": config.UI_LANGUAGE,
            "hymoWarningDismissed": config.UI_HYMO_WARNING_DISMISSED,
            "env": {
                "ACCESS_TOKEN_LIST": config.ACCESS_TOKEN_LIST or "",
                "ACCESS_TOKEN_DOWNLOAD": config.ACCESS_TOKEN_DOWNLOAD or "",
                "USER_ID": config.USER_ID or "",
                "DROPBOX_APP_KEY": config.DROPBOX_APP_KEY or "",
                "DROPBOX_APP_SECRET": config.DROPBOX_APP_SECRET or "",
                "DROPBOX_REFRESH_TOKEN": config.DROPBOX_REFRESH_TOKEN or "",
            },
            "config": {
                "logging": {"level": config.LOG_LEVEL},
                "network": {
                    "min_delay": config.MIN_DELAY,
                    "max_delay": config.MAX_DELAY,
                    "timeout": config.NETWORK_TIMEOUT,
                    "page_size": config.PAGE_SIZE,
                },
                "paths": {
                    "download": {"clean_download_after_copy": config.CLEAN_DOWNLOAD},
                    "setups": {
                        "overwrite": config.OVERWRITE,
                        "delete_previous_version": config.DELETE_PREVIOUS_VERSION,
                    },
                },
                "remote_mappings": {
                    "enabled": config.REMOTE_MAPPINGS_ENABLED,
                    "url": config.REMOTE_MAPPINGS_URL,
                    "timeout": config.REMOTE_MAPPINGS_TIMEOUT,
                },
                "dropbox": {
                    "folder": config.DROPBOX_FOLDER,
                    "timeout": config.DROPBOX_TIMEOUT,
                    "upload_workers": config.DROPBOX_UPLOAD_WORKERS,
                },
            },
        }

    def _installed_summary(self) -> tuple[bool, int]:
        # DB_PATH is not mode-conditional (core/config.py sets it regardless of
        # MODE), so it reflects whatever full/slave runs have installed on this
        # machine even while the app is currently set to master - show it as-is
        # rather than hiding it, since master not writing to the DB itself is not
        # the same as there being nothing worth showing.
        from domain.setup_db import SetupDb
        database = SetupDb()
        return True, len(database.fetch_all_installed_setups())

    # ----- setup installati tab ---------------------------------------------

    def list_installed_setups(self, search: str, unmapped_only: bool) -> dict[str, object]:
        from domain.setup_db import SetupDb, InstalledSetup

        database = SetupDb()
        setups: list[InstalledSetup] = database.fetch_all_installed_setups()

        query: str = (search or "").strip().lower()
        filtered: list[InstalledSetup] = [
            s for s in setups
            if (not unmapped_only or not s.track_found)
            and (not query or query in s.track.lower() or query in s.car.lower())
        ]

        # Group by the matched LMU folder when the track resolved, not by the raw
        # API track name: TrackTitan exposes the same physical track under
        # different raw names (e.g. "Bahrain - WEC" vs "Bahrain International
        # Circuit"), which both resolve to the same matched_track_id and should
        # collapse into a single card. Unmapped setups have no matched id, so they
        # still group (and stay individually correctable) by their raw track text.
        groups: dict[str, list[InstalledSetup]] = {}
        for s in filtered:
            key = s.matched_track_id if (s.track_found and s.matched_track_id) else s.track
            groups.setdefault(key, []).append(s)

        grouped: list[dict[str, object]] = [
            {
                "track": track,
                "trackFound": items[0].track_found,
                "cars": self._group_by_car_and_type(items),
            }
            for track, items in sorted(groups.items())
        ]

        return {"groups": grouped, "totalCount": len(filtered), "grandTotal": len(setups)}

    def _group_by_car_and_type(self, items: list["InstalledSetup"]) -> list[dict[str, object]]:
        # A car can have both a HYMO (TrackTitan) and a GO (third-party) setup
        # installed at once; without this, each showed as its own duplicate
        # "car" row. One entry per car instead, holding whichever of its
        # HYMO/GO sub-groups actually have installed setups.
        by_car: dict[str, dict[str, list[InstalledSetup]]] = {}
        for s in items:
            by_car.setdefault(s.car, {}).setdefault(s.setup_type, []).append(s)

        return [
            {
                "car": car,
                "types": [
                    {"type": setup_type, "setups": [self._serialize_installed(s) for s in entries]}
                    for setup_type in ("HYMO", "GO")
                    if (entries := by_type.get(setup_type))
                ],
            }
            for car, by_type in sorted(by_car.items())
        ]

    def _serialize_installed(self, setup: "InstalledSetup") -> dict[str, object]:
        return {
            "setupId": setup.setup_id,
            "track": setup.track,
            "car": setup.car,
            "installDate": setup.install_date,
            "hotlapLink": setup.hotlap_link,
            "fileCount": len(setup.file_names),
            "fileNames": setup.file_names,
            "installationFolder": setup.installation_folder,
            "installationBasePath": setup.installation_base_path,
            "trackFound": setup.track_found,
            "setupType": setup.setup_type,
        }

    def delete_setup(self, setup_id: str) -> dict[str, object]:
        from domain.setup_db import SetupDb
        from processing.car_manager import CarManager
        from processing.track_manager import TrackManager
        from processing.setup_manager import SetupManager

        database = SetupDb()
        setup_manager = SetupManager(track_manager=TrackManager(), car_manager=CarManager(), database=database)
        return {"deleted": setup_manager.delete_setup(setup_id)}

    def delete_setups(self, setup_ids: list[str]) -> dict[str, object]:
        from domain.setup_db import SetupDb
        from processing.car_manager import CarManager
        from processing.track_manager import TrackManager
        from processing.setup_manager import SetupManager

        database = SetupDb()
        setup_manager = SetupManager(track_manager=TrackManager(), car_manager=CarManager(), database=database)
        deleted_count = sum(1 for setup_id in setup_ids if setup_manager.delete_setup(setup_id))
        return {"deletedCount": deleted_count}

    def delete_all_setups(self) -> dict[str, object]:
        # Sources setup_ids from the database itself rather than trusting a
        # client-supplied list, so "delete all" always covers every installed
        # setup regardless of whatever search/filter the frontend currently
        # has applied to its own copy of the data.
        from domain.setup_db import SetupDb
        from processing.car_manager import CarManager
        from processing.track_manager import TrackManager
        from processing.setup_manager import SetupManager

        database = SetupDb()
        setup_manager = SetupManager(track_manager=TrackManager(), car_manager=CarManager(), database=database)
        setup_ids = [s.setup_id for s in database.fetch_all_installed_setups()]
        deleted_count = sum(1 for setup_id in setup_ids if setup_manager.delete_setup(setup_id))
        return {"deletedCount": deleted_count}

    def get_track_folder_options(self) -> list[str]:
        from processing.track_manager import TrackManager
        return TrackManager().get_known_folder_names()

    def map_track(self, track: str, folder: str) -> dict[str, object]:
        from processing.car_manager import CarManager
        from processing.track_manager import TrackManager
        from processing.setup_manager import SetupManager
        from domain.setup_db import SetupDb

        track_manager = TrackManager()
        track_manager.add_or_update_mapping(track, folder)
        track_manager.refresh()

        database = SetupDb()
        setup_manager = SetupManager(track_manager=track_manager, car_manager=CarManager(), database=database)
        setup_manager.update_tracks_not_found()

        return {}

    # ----- download tab ------------------------------------------------------

    def validate_start(self, mode: str) -> list[str]:
        from core.config import check_credentials, MOCK_TRACKTITAN, MOCK_DROPBOX, MOCK_LMU, LMU_SETUPS_BASE_PATH
        errors = check_credentials(mode, MOCK_TRACKTITAN, MOCK_DROPBOX)
        # Only Full and Slave install setups locally, so only they depend on
        # LMU_SETUPS_BASE_PATH existing - Master only ever uploads to Dropbox.
        # Kept out of check_credentials(), which validates secrets, not paths.
        if mode in {"full", "slave"} and not MOCK_LMU and not Path(LMU_SETUPS_BASE_PATH).exists():
            errors.append("Invalid or missing LMU_PATH")
        return errors

    def check_lmu_path(self, path: str) -> bool:
        return bool(path) and Path(path).exists()

    def start_download(self, mode: str) -> dict[str, object]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {"started": False, "reason": "already-running"}
            cancel_event = threading.Event()
            self._cancel_event = cancel_event
            self._running = True
            self._last_error = None

        def worker() -> None:
            from core.errors import AuthError

            try:
                run_fn = self._resolve_run_fn(mode)
                run_fn(log, on_progress=self._push_progress, cancel_event=cancel_event)
            except AuthError as e:
                self._last_error = str(e)
                self._push_progress(ProgressEvent(
                    kind=ProgressKind.ERROR,
                    title=str(e),
                    is_auth_error=True,
                    error_code=e.code,
                    error_status=e.status,
                ))
                log.exception("Download run failed: authentication error")
            except Exception as e:
                self._last_error = str(e)
                self._push_progress(ProgressEvent(kind=ProgressKind.ERROR, title=str(e)))
                log.exception("Download run failed")
            finally:
                self._running = False

        thread = threading.Thread(target=worker, daemon=True)
        self._thread = thread
        thread.start()
        return {"started": True}

    def _resolve_run_fn(self, mode: str) -> Callable[..., None]:
        import main
        run_fns: dict[str, Callable[..., None]] = {
            "full": main.run_full,
            "master": main.run_master,
            "slave": main.run_slave,
        }
        if mode not in run_fns:
            raise ValueError(f"Unknown mode: {mode}")
        return run_fns[mode]

    def stop_download(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def get_status(self) -> dict[str, object]:
        return {"running": self._running, "lastError": self._last_error}

    def _push_progress(self, event: ProgressEvent) -> None:
        if self._window is None:
            return
        payload: str = json.dumps({
            "kind": event.kind.value,
            "title": event.title,
            "meta": event.meta,
            "authError": event.is_auth_error,
            "errorCode": event.error_code,
            "errorStatus": event.error_status,
        })
        try:
            self._window.evaluate_js(f"window.onProgress && window.onProgress({payload})")
        except Exception as e:
            log.debug(f"Failed to push progress to the window: {e}")

    # ----- settings tab -------------------------------------------------------

    def browse_lmu_folder(self, current: str) -> Optional[str]:
        if self._window is None:
            return None
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=current or "")
        if not result:
            return None
        return result[0]

    def save_settings(self, env_values: dict[str, str], config_patch: dict[str, object]) -> None:
        from core.config import save_env_values, save_config

        if env_values:
            save_env_values(env_values)
        if config_patch:
            save_config(config_patch)
        self._reload_config()
        self._settings_dirty = False

    def mark_settings_dirty(self, dirty: bool) -> None:
        self._settings_dirty = dirty

    def _handle_window_closing(self) -> bool:
        """Bound to webview's `events.closing` (window.py), which fires on the
        native FormClosing event. Returning False cancels the close; with
        unsaved Settings edits pending, cancel it and ask the frontend to
        confirm save/discard first - confirm_close() below re-fires the actual
        close once the user resolves that prompt (setting Cancel = False and
        letting FormClosing continue to completion this second time around).
        """
        if not self._settings_dirty:
            return True
        if self._window is not None:
            try:
                self._window.evaluate_js("window.onRequestCloseConfirmation && window.onRequestCloseConfirmation()")
            except Exception as e:
                log.debug(f"Failed to request close confirmation: {e}")
        return False

    def confirm_close(self) -> None:
        self._settings_dirty = False
        if self._window is not None:
            self._window.destroy()

    def _reload_config(self) -> None:
        """Refresh every module's config-derived globals in place, so a settings
        save takes effect immediately instead of requiring a full relaunch.

        core.config is reloaded first (it re-reads .env/config.json from disk),
        then each module in _HOT_RELOAD_MODULES - only if already imported, since
        they're all lazy-imported on the first Start Download click. No live
        instances survive a reload: every run constructs fresh manager/client
        objects, so redefining their classes mid-process is safe.
        """
        import core.config as config
        importlib.reload(config)
        for name in _HOT_RELOAD_MODULES:
            module = sys.modules.get(name)
            if module is not None:
                importlib.reload(module)

        import main
        main.apply_log_level(config.LOG_LEVEL)

    def set_language(self, language: str) -> None:
        # No relaunch needed: the frontend re-renders instantly against the other
        # TRANSLATIONS dict; only the persisted choice matters for next launch.
        from core.config import save_config
        save_config({"ui": {"language": language}})

    def dismiss_hymo_warning(self) -> None:
        from core.config import save_config
        save_config({"ui": {"hymo_warning_dismissed": True}})

    def open_external_link(self, url: str) -> None:
        webbrowser.open(url)

    def simulate_paste_shortcut(self) -> None:
        # Backs the custom text-field context menu's Paste item (app.js's
        # contextMenuPaste): WebView2 blocks JS clipboard reads here without a
        # permission grant it never prompts for, and its execCommand("paste")
        # fallback is a documented bug (MicrosoftEdge/WebView2Feedback#1945)
        # that can insert the wrong content instead of pasting. A real Ctrl+V
        # keypress already works correctly since WebView2 handles it natively,
        # so this injects that same keystroke at the OS input-queue level -
        # indistinguishable to WebView2 from the user physically pressing it,
        # landing in whatever field currently has focus (the caller must
        # field.focus() first).
        import ctypes

        KEYEVENTF_KEYUP = 0x0002
        VK_CONTROL = 0x11
        VK_V = 0x56
        user32 = ctypes.windll.user32
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

    def dropbox_oauth_get_url(self, app_key: str, app_secret: str, token_type: str = "read_write") -> dict[str, object]:
        from clients.dropbox_client import get_authorization_url, READ_ONLY_SCOPES, READ_WRITE_SCOPES
        scope = READ_ONLY_SCOPES if token_type == "read_only" else READ_WRITE_SCOPES
        try:
            return {"url": get_authorization_url(app_key, app_secret, scope=scope)}
        except Exception as e:
            log.warning(f"Failed to start Dropbox OAuth flow: {e}")
            return {"error": str(e)}

    def dropbox_oauth_exchange_code(self, app_key: str, app_secret: str, code: str) -> dict[str, object]:
        from clients.dropbox_client import exchange_authorization_code
        try:
            return {"refreshToken": exchange_authorization_code(app_key, app_secret, code)}
        except Exception as e:
            log.warning(f"Failed to exchange Dropbox authorization code: {e}")
            return {"error": str(e)}

    # ----- TrackTitan automatic token fetch ------------------------------------
    # Unlike the Dropbox flow above (system browser + a code the user pastes
    # back), TrackTitan's tokens are never shown to the user anywhere - they
    # live in Cognito-style session cookies set after login. So instead this
    # opens a second pywebview window on the login page, lets the user log in
    # normally, and polls that window's cookies in a background thread until
    # the three expected ones show up (or the user cancels, or it times out).

    _TT_POLL_INTERVAL_SECONDS = 1.0
    _TT_TIMEOUT_SECONDS = 300.0

    def tracktitan_fetch_tokens_start(self) -> dict[str, object]:
        from clients.track_titan_client import TRACKTITAN_LOGIN_URL

        with self._tt_lock:
            if self._tt_thread is not None and self._tt_thread.is_alive():
                return {"started": False, "reason": "already-running"}

            cancel_event = threading.Event()
            self._tt_cancel_event = cancel_event
            child = webview.create_window(
                title="TrackTitan Login",
                url=TRACKTITAN_LOGIN_URL,
                width=480,
                height=760,
                on_top=True,
            )
            self._tt_window = child
            # Covers the user closing the popup by hand (as opposed to
            # tracktitan_fetch_tokens_cancel(), the "Annulla" button) - either
            # way the poll loop below treats it the same, as a cancellation.
            child.events.closed += lambda: cancel_event.set()

            thread = threading.Thread(
                target=self._run_tracktitan_fetch, args=(child, cancel_event), daemon=True
            )
            self._tt_thread = thread
            thread.start()
        return {"started": True}

    def tracktitan_fetch_tokens_cancel(self) -> None:
        # Destroys the window immediately (rather than waiting for the poll
        # loop's next iteration) so the "Annulla" button feels instant.
        if self._tt_cancel_event is not None:
            self._tt_cancel_event.set()
        self._close_tt_window()

    def _run_tracktitan_fetch(self, child: webview.Window, cancel_event: threading.Event) -> None:
        from clients.track_titan_client import extract_tokens_from_cookies

        deadline = time.monotonic() + self._TT_TIMEOUT_SECONDS
        tokens: Optional[dict[str, str]] = None
        reason = "timeout"
        while time.monotonic() < deadline:
            if cancel_event.is_set():
                reason = "cancelled"
                break
            try:
                raw_cookies = child.get_cookies()
            except Exception:
                # The window is gone (destroyed by the user or by us mid-poll).
                reason = "cancelled"
                break
            cookies = {key: morsel.value for cookie in raw_cookies for key, morsel in cookie.items()}
            tokens = extract_tokens_from_cookies(cookies)
            if tokens is not None:
                reason = "ok"
                break
            cancel_event.wait(self._TT_POLL_INTERVAL_SECONDS)

        # Destroy child directly - self._tt_window may already be cleared if
        # tracktitan_fetch_tokens_cancel() got there first.
        try:
            child.destroy()
        except Exception:
            pass
        if self._tt_window is child:
            self._tt_window = None
        self._push_tracktitan_tokens(reason, tokens)

    def _close_tt_window(self) -> None:
        if self._tt_window is not None:
            try:
                self._tt_window.destroy()
            except Exception:
                pass
            self._tt_window = None

    def _push_tracktitan_tokens(self, reason: str, tokens: Optional[dict[str, str]]) -> None:
        if self._window is None:
            return
        payload: str = json.dumps({"ok": reason == "ok", "reason": reason, "tokens": tokens or {}})
        try:
            self._window.evaluate_js(f"window.onTrackTitanTokens && window.onTrackTitanTokens({payload})")
        except Exception as e:
            log.debug(f"Failed to push TrackTitan tokens to the window: {e}")
