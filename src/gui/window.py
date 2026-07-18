import ctypes
import logging
import sys
import traceback

import webview

from core.utils import get_path
from gui.api import Api


def _index_html_path() -> str:
    # get_path() resolves relative to BASE_DIR, which is the repo root in dev
    # (core.utils.get_base_dir()'s parents[2]) but the exe's own directory once
    # frozen. The source tree ships these assets under src/gui/web/, while
    # build.bat copies them next to the frozen exe as gui/web/ (flattened, no
    # src/ prefix) - so which relative path is correct depends on which case
    # this is.
    relative = "gui/web/index.html" if getattr(sys, "frozen", False) else "src/gui/web/index.html"
    return str(get_path(relative))


def launch() -> None:
    # This is now the only place a startup crash can surface: there is no console
    # fallback left anywhere in the app once GUI-only lands.
    try:
        from main import setup_logging, _log_sandbox  # also forces a settings.db open/seed
        log = setup_logging()
        _log_sandbox(log)
        api = Api()
        window = webview.create_window(
            title="LMU Setup Manager",
            url=_index_html_path(),
            js_api=api,
            width=1200,
            height=800,
            min_size=(960, 640),
        )
        # The window object does not exist until create_window() returns, so the
        # back-reference api needs for evaluate_js()/create_file_dialog() can only
        # be bound after this point (standard pywebview idiom). Must stay
        # underscore-prefixed (Api._window) - see the comment on Api.__init__.
        api._window = window
        webview.start()
    except Exception as e:
        message = f"LMU Setup Manager failed to start:\n\n{e}\n\n{traceback.format_exc()}"
        # A fresh getLogger() call, not the `log` local: if setup_logging() itself
        # raised, `log` was never assigned, and referencing it would raise
        # NameError and mask the real error. Absorbed silently if no handlers got attached.
        logging.getLogger("TrackTitanDownloader").exception("Fatal startup error")
        try:
            ctypes.windll.user32.MessageBoxW(None, message, "LMU Setup Manager - Fatal error", 0x10)
        except Exception:
            # Last resort if even the message box fails (e.g. not on Windows).
            print(message)
