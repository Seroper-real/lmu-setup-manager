# Implement HYMO Dashboard design into lmu-setup-manager

## Context

The user maintains `lmu-setup-manager`, a Python desktop app (entry point `src/main.py`) that downloads
"HYMO"-branded setups from **TrackTitan** for the racing sim *Le Mans Ultimate* and installs them locally,
optionally relaying through the user's own Dropbox. It has three modes:
- **full** ("Direct"): download from TrackTitan, install locally.
- **master** ("Upload only"): download from TrackTitan, push to the user's Dropbox.
- **slave** ("Install only"): pull from the user's Dropbox, install locally.

A separate third-party provider, **GO Setups**, piggybacks on the Dropbox tree in `slave` mode only.

The user used the Claude Design product to prototype a full redesign of the app's dashboard UI
(`HYMO Dashboard.dc.html`, imported via the `DesignSync` MCP tool from project
`e3c73bba-52dd-4857-af41-8135e141fe03`). This is a **React-ish mock prototype** (Claude Design's `.dc.html`
format: a `<x-dc>` template with `{{ binding }}` placeholders + a `<script type="text/x-dc" data-dc-script">`
class extending `DCLogic`, driven entirely by **fake/mock in-memory state** — there is no real backend wiring).
The task: reimplement this dashboard's look, structure and interaction design in the **real app**, replacing
the mockup's fake state/handlers with the app's actual data (SetupManager/CarManager, config, i18n, mode
logic, etc.), and swap the mockup's `uploads/*.png` car-class-logo images for the repo's own
`assets/class-logos/{HYPERCAR,GT3,GTE,P2,P3}.png`.

## Design summary (from HYMO Dashboard.dc.html)

- **Theme**: "Nocturne" dark design system (`_ds/nocturne-.../styles.css`) — dark navy background
  (`--color-bg:#161826`), blurple accent (`--color-accent:#9184d9`), Inter font, card/button/tag/table/dialog
  component classes documented in that stylesheet.
- **Layout**: fixed left sidebar (232px) with logo/app name, 4 nav items (icons + label), and a footer
  block showing active mode badge + total installed count + app version. Main content area is a single
  active tab, no page scroll on the sidebar.
- **Tabs**:
  1. **Setup installati / Installed setups** — search box, "to map" filter toggle, results count, "delete
     all" button. List of **track groups** (collapsible) → **car groups** (collapsible, car-class logo icon)
     → **setup entries** (collapsible, expandable to show file names), each entry showing a type tag
     (HYMO/GO/CUSTOM), date, file count, install folder, optional hotlap YouTube link, delete (single /
     bulk-by-type) actions. Unmapped tracks show a "Fix" (Correggi) action + dialog to map to an LMU folder.
  2. **Download** — shows active mode + a "Change" shortcut to Settings, a status card (idle/running/
     completed/stopped) with Start/Stop button, and a scrolling activity log.
  3. **Carica Setup / Upload** — manual .zip upload dropzone, then a form to assign Type/Track/Car
     (searchable dropdowns, car dropdown shows class logos) before confirming.
  4. **Impostazioni / Settings** — mode picker (3 cards), language toggle (it/en), LMU install path field
     (with browse-folder + copy), TrackTitan token fields (ACCESS_TOKEN_LIST, ACCESS_TOKEN_DOWNLOAD,
     USER_ID) with reveal/copy/"Get automatically" fetch flow, Dropbox fields (APP_KEY, APP_SECRET,
     REFRESH_TOKEN, folder) with reveal/copy/OAuth flow, and a collapsible "Advanced" section (log level,
     network page size/timeout/min-max delay, download/setup behavior checkboxes, remote-tracks
     enable/url/timeout, Dropbox timeout/upload-workers).
- **Global dialogs**: first-run warning, track-fix ("Correggi") dialog, delete-confirm dialog (single/
  type-bulk/track-bulk/all variants), delete-all progress dialog, start-validation-error dialog (missing
  tokens/Dropbox/LMU path per mode), Dropbox OAuth choice + code dialogs, TrackTitan fetch-in-progress
  dialog, unsaved-settings-changes prompt (guards leaving Settings tab), and a bottom-right toast.
- **Car class logos**: mockup maps each of ~24 hardcoded car names to one of 5 classes
  (HYPERCAR/GT3/GTE/P2/P3) via a `CAR_CLASS_MAP` and renders `uploads/<Class>.png`. In the real
  implementation this must use `assets/class-logos/{HYPERCAR,GT3,GTE,P2,P3}.png` and the **real**
  car→class source of truth (CarManager), not the mockup's hardcoded map/list.
- All mock data (`cloneMockGroups()`, `DOWNLOAD_SCRIPT_BY_LANG`, hardcoded `CAR_OPTIONS`/
  `TRACK_FOLDER_OPTIONS`) and simulated behaviors (fake setInterval download/delete-all progress) are
  prototype-only and must be replaced by real backend calls.

## Current architecture (verified directly + via exploration)

The app already has a **fully working dashboard**, itself built by hand-porting an earlier revision of
this exact same Claude Design project (confirmed: the new mock's nocturne CSS tokens are byte-for-byte
identical to `src/gui/web/styles.css`'s section 1). GUI = **pywebview** (native window embedding a system
webview, `requirements.txt`), not a browser/Electron — plain hand-written HTML/CSS/JS, no build step,
entry `src/gui/window.py:launch()` → `src/main.py`.

- `src/gui/web/index.html` — static shell: sidebar (`#nav`, footer with mode-badge/installed-count/
  version) + `<main>` with three `<section class="view" id="view-setups|view-download|view-settings">`
  + `#modal-root` + `#toast-root`. Scripts: `i18n.js`, `app.js`.
- `src/gui/web/app.js` (~1770 lines) — one global `state` object, per-view `render*View()` functions that
  replace `innerHTML` wholesale, inline-SVG `ICONS` object (no `<img>` tags anywhere today).
  `renderSetupsView/renderTrackGroup/renderCarGroup/renderSetupEntry` (404-646),
  `renderDownloadView` (658-738), `renderSettingsView`/`renderAdvancedFields` (877-1117),
  `renderSidebar`/`goToView` (319-400), `renderModals` (1236-1583, all dialogs incl. a real-app-only
  mid-run auth-error dialog the mock doesn't have).
- `src/gui/web/styles.css` — section 1 = nocturne tokens/components (verbatim, unchanged by the new mock),
  section 2 = this app's own layout classes.
- `src/gui/web/i18n.js` — `TRANSLATIONS.it/.en` (mock-derived) + `EXTRA` (real-app-only strings), looked up
  via `state.language`.
- `src/gui/api.py` (`class Api`) — the JS↔Python bridge (`window.pywebview.api.*`). Already exposes
  everything the 3 existing tabs need: `get_bootstrap()`, `list_installed_setups`/`_group_by_car_and_type`
  (hardcodes `("HYMO","GO")` at `api.py:215` — silently drops any other `setup_type`, a real latent bug),
  `_serialize_installed`, `delete_setup(s)`/`delete_all_setups`, `get_track_folder_options`/`map_track`,
  `validate_start`/`start_download`/`stop_download`/`get_status`, `save_settings`, `browse_lmu_folder`
  (uses `self._window.create_file_dialog(webview.FileDialog.FOLDER, ...)` — the real native-dialog pattern
  to imitate for the zip picker), Dropbox OAuth + TrackTitan auto-fetch methods, `set_language`.
- Backend: `SetupManager.install_setup(downloaded_path, setup: Setup, extensions, setup_type,
  fallback_suffix, sha256)` is the single real entry point for installing ANY setup (TrackTitan, GO, or —
  new — manual). `Setup` wraps a TrackTitan-API-shaped `data` dict; a synthetic one can be built the same
  way `SlaveManager._process_go` does for GO archives. `CarManager.get_car_name()` resolves a raw car
  string via `config/mapping.json`'s `"cars"` list (34 entries, each `{name, class, matcher}` — class
  values `hypercar|lmgt3|lmgte|lmp2|"lmp2 (elms)"|lmp3`), but `catalog_loader.compile_patterns()` currently
  **discards the `class` field** — no car→class lookup exists anywhere yet. `TrackManager` is the track
  equivalent (+ a per-user "Correggi" override layer for unmapped tracks, in `settings_db`'s `tracks` table).
  Modes are plain strings (`full`/`master`/`slave`), dispatched via `main.run_full/run_master/run_slave` and
  `MasterManager`/`SlaveManager` orchestration classes. `MasterManager._publish`/`_build_package` (lines
  160-232) show exactly how a setup gets repackaged + uploaded to Dropbox with an embedded
  `.metadata.json` — the pattern the new manual-upload-to-Dropbox path must mirror.
- `build.bat` — PyInstaller `--onefile --windowed`, then `xcopy /Y /E /I src\gui\web dist\gui\web\` (copies
  the **entire** `src/gui/web/` tree recursively — any new subfolder placed inside it ships automatically,
  in both dev and packaged-exe paths, with zero `build.bat` changes needed).
- `assets/class-logos/{HYPERCAR,GT3,GTE,P2,P3}.png` exist at the repo **root**, uniformly named — nothing
  makes them servable to the webview today (no `file://`/relative-path convention exists yet for images).

## Decisions locked in with the user

1. **"Carica Setup" / Upload tab must be fully wired**, not stubbed: a real native `.zip` file picker, real
   track/car dropdown data from `config/mapping.json`, and a real install (full/slave) or Dropbox-upload
   (master) on confirm.
2. **Car-class logos** must be threaded end-to-end (mapping.json → CarManager → Api payload → `<img>` in
   `app.js`), reusing the existing `assets/class-logos/*.png` — copy them into a new
   `src/gui/web/assets/class-logos/` folder so pywebview can actually load them (keep the repo-root copies
   as-is; don't delete them).
3. **Drop the mock's "CUSTOM" manual-upload type option.** Only `HYMO` and `GO Setups` are real, recognized
   installable conventions (HYMO's branded-zip+metadata format; GO's 3-segment-path format) — there's no
   third convention a Dropbox-relay run could later recognize. The real Upload tab's Type dropdown offers
   only these two.

## Implementation plan

### 1. Car-class logos (touches `catalog_loader.py`, `car_manager.py`, `api.py`, `app.js`)
- `catalog_loader.py`: add `extract_value_map(entries, *, name_key, value_key) -> dict[str,str]` next to
  `compile_patterns()` (optional field, silently skips entries missing it — unlike `name_key`).
- `car_manager.py`: add a `_CLASS_LABELS` map (`hypercar→HYPERCAR`, `lmgt3→GT3`, `lmgte→GTE`,
  `lmp2`/`"lmp2 (elms)"→P2`, `lmp3→P3`) and `_normalize_class()`. Rework `build_car_patterns()` to capture
  `self.car_classes: dict[str,str]` and `self._car_entries` in the same load (mirrors
  `TrackManager.build_track_patterns()`'s multi-field pattern — no extra network round trip). Add
  `get_car_class(name) -> str|None` and `get_all_cars() -> list[{"name","carClass"}]` (preserves
  mapping.json's own ordering, for the Upload tab's car dropdown).
- `api.py`: cache one `CarManager` on the `Api` instance (constructing it fresh per call would re-parse —
  and potentially re-fetch remotely — `mapping.json` on every debounced search keystroke; invalidate it the
  same way `_reload_config()` already hot-reloads other modules). Add `carClass` to each car group in
  `_group_by_car_and_type`, and while there, **fix the hardcoded `("HYMO","GO")` tuple** (line 215) to
  preserve that ordering first but no longer silently drop other `setup_type` values. Add
  `get_car_options() -> list[dict]` (delegates to `CarManager.get_all_cars()`) for the Upload tab.
- `app.js`: in `renderCarGroup()`, add one templated `<img class="car-class-logo"
  src="assets/class-logos/${carGroup.carClass}.png">` when `carClass` is set (simpler than the mock's 5
  `sc-if` branches, since real assets are uniformly named `<CLASS>.png` unlike the mock's fixture
  filenames). Reuse the same `<img>` pattern in the new Upload tab's car dropdown (§3).
- One-time file copy (not a build step): copy the 5 PNGs from `assets/class-logos/` into a new
  `src/gui/web/assets/class-logos/`.

### 2. Mode-picker relocation (touches `app.js`, `i18n.js`)
The mock moves the full, clickable 3-mode-card picker from Download onto Settings (mock lines 437-450),
and replaces it on Download (and the new Upload tab) with a compact read-only summary card + "Cambia
modalità" button that navigates to Settings. Move the existing mode-card markup + `set_mode()` wiring out
of `renderDownloadView()` into a new section at the top of `renderSettingsView()`; replace it in
`renderDownloadView()`/`renderUploadView()` with the compact card. Keep `state.selectedMode` out of the
Settings unsaved-changes snapshot, exactly as it is today (it's a separately-persisted, immediately-applied
value, not a form field). Add new i18n keys: `modeGeneralFullDesc/MasterDesc/SlaveDesc` (Settings' picker),
`uploadFullDesc/MasterDesc/SlaveDesc` (Upload tab's summary card) — `fullDesc/masterDesc/slaveDesc` already
exist and stay for Download's summary card.

### 3. New "Carica Setup" / Upload tab (touches `index.html`, `app.js`, `i18n.js`, `styles.css`, `api.py`,
   new `src/processing/manual_upload.py`)
- `index.html`: add `<section class="view" id="view-upload"></section>` between download/settings.
- `app.js`: add a nav entry + `ICONS.navUpload` (copy the mock's glyph), call `renderUploadView()` from
  `render()`. New state: `manualUpload` (`{filePath, fileName, type, track, car}` or `null`),
  dropdown-open/search fields, `carOptions` (lazy-fetched once via `get_car_options()`, mirroring how
  `state.trackFolderOptions` is already lazy-fetched for the Correggi modal). Dropzone `onClick` calls
  `api().pick_setup_zip_file()` **directly** (no hidden `<input type=file>` — pywebview's bridge would
  otherwise need to base64-serialize the zip's bytes across the wire; a native dialog just hands back a
  real path). Type dropdown: **`HYMO` / `GO Setups` only** (per decision #3). Track dropdown: reuses
  `get_track_folder_options()` as-is. Car dropdown: new `get_car_options()`, shows the class-logo `<img>`
  per option. Confirm handler: calls `api().validate_start(state.selectedMode)` first (reusing the exact
  same pre-flight credential/path validation dialog the Download tab's Start button uses — no new dialog
  needed), then `api().upload_manual_setup(filePath, type, track, car)`; on success, refresh the Setups tab
  data if not in `master` mode.
- `api.py`: add `pick_setup_zip_file()` (mirrors `browse_lmu_folder`, uses
  `webview.FileDialog.OPEN, file_types=("Zip files (*.zip)",)` — confirmed a real, supported pywebview 6.2.1
  parameter) and `upload_manual_setup(zip_path, setup_type, track, car)`, which validates, builds a
  synthetic `Setup` via the new `manual_upload.py` helper, and branches on `self.current_mode()`:
  `master` → package + `dropbox_client.upload(...)` (mirrors `MasterManager._publish`/`_build_package`,
  embedding the same `.metadata.json`); `full`/`slave` → stage a copy under `DOWNLOAD_PATH` (never hand
  `install_setup()` the user's original file directly — it takes ownership and may delete it) and call
  `SetupManager.install_setup(..., setup_type=type, fallback_suffix=type)`. Wrap in the same `AuthError`
  handling pattern `start_download()` uses.
- `manual_upload.py` (new): `build_manual_setup(track, car) -> Setup`, `install_manual_setup_locally(...)`,
  `upload_manual_setup_to_dropbox(...)` — keeps `api.py` a thin dispatcher, matching how `SetupManager`/
  `MasterManager`/`SlaveManager` are already factored out as independently testable classes.
- i18n: add `navUpload`, `uploadPageTitle/Desc`, `uploadDropzoneTitle/Desc`, `changeModeButton`,
  `manualUploadTypeLabel/TrackLabel/CarLabel` + placeholders, `manualUploadSearchPlaceholder/NoResults`,
  `manualUploadCancel/Confirm`, `manualUploadSuccessToast`, plus one real-app-only
  `manualUploadGenericErrorToast` (`EXTRA` family) — values copied from the mock's `it`/`en` blocks, minus
  the vestigial `manualUploadButton`/`manualUploadDialogTitle` keys (unreferenced in the mock's own output)
  and anything CUSTOM-specific.
- styles.css: small additions (`.upload-dropzone`, `.select-dropdown/.select-panel/.select-option`,
  `.mode-summary` shared with Download, `.car-class-logo`), built from existing tokens only.

### 4. Bundled correctness fix: Correggi folder round-trip
Exposing `get_track_folder_options()`'s folder names as directly-selectable values in the new Upload tab's
Track dropdown surfaces a latent bug: `TrackManager.add_or_update_mapping(track, folder)` stores a pattern
that matches the original raw TrackTitan track text, not the folder name itself — so picking a
user-Correggi'd folder name (rather than a built-in, self-matching mapping.json track name) from the new
dropdown would resolve to a wrong, newly-created folder instead of the intended existing one. Fix by also
registering a self-matching pattern for the folder name itself when a Correggi mapping is saved, so the
folder name becomes a valid resolution target on its own.

## Verification

- `pytest` (existing suite, esp. `tests/unit/test_car_manager.py`, `tests/unit/test_gui_api.py` — extend
  both for `get_car_class`/`get_all_cars`/`carClass` payload field, the `_group_by_car_and_type` ordering
  fix, and the new `manual_upload.py` module).
- Run the app via `python src/main.py --sandbox` (per `readme.md`'s documented sandbox flags — no real
  TrackTitan/Dropbox/LMU needed) and manually exercise: Setup installati tab shows car-class logos; Download
  tab shows the compact mode summary + still starts/stops a sandbox run; Settings tab shows the new
  mode-picker section and still saves; new Carica Setup tab — pick a zip via the native dialog, assign
  HYMO/GO + a track + a car, confirm, and verify it lands in `sandbox/lmu/Settings/` (full/slave) or
  `sandbox/dropbox/` (master) and then shows up back in the Setup installati list.
- `python src/main.py --sandbox --mode master` then manually upload a setup, confirm the Dropbox mock
  received a correctly-named/placed zip with embedded metadata; then `--sandbox --mode slave` and confirm
  `SlaveManager` picks it back up as a normal HYMO/GO install.
- Spot-check a Correggi-mapped track's folder name through the new Upload tab's Track dropdown to confirm
  the round-trip fix (§4) actually resolves to the existing folder, not a new "<folder> - HYMO" one.
