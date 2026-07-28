# Add "Mappature manuali" tab from the updated HYMO Dashboard mockup

## Context

The user maintains `lmu-setup-manager`, a Python/pywebview desktop app that downloads "HYMO"-branded
setups (from TrackTitan) and/or GO Setups files for *Le Mans Ultimate*, installing them locally or
relaying through Dropbox. Its dashboard UI was previously reimplemented from a Claude Design "Nocturne"
mockup (this same `plan.md` used to document that pass — see git history for the prior version — already
shipped and verified). Since then, two more features shipped directly in code (no matching mockup at the
time): an "unmatched setup" tracking system that **skips** installing setups whose track/car text doesn't
match anything, and a `manual_mapping` SQLite table (`src/core/settings_db.py`) that stores user
corrections — created exclusively through an end-of-run **stepper dialog** (`state.unmatchedTarget` in
`app.js`) that walks each unmatched item and lets the user pick the right track and/or car.

The user has now imported a **new revision** of the same Claude Design project
(`HYMO Dashboard.dc.html`, project `e3c73bba-52dd-4857-af41-8135e141fe03`), asking for it to be
implemented. Its only substantive addition versus what's already shipped is a new **"Mappature manuali" /
"Associazioni manuali"** nav tab: a searchable, paginated table that browses and deletes existing
`manual_mapping` rows (Type/Name/Matcher/Actions columns, per-row delete, delete-all, both with confirm
dialogs + toasts). It has no "add mapping" form — rows keep being created only by the existing stepper.

The mockup also depicts a different, simpler correction UI directly inside "Setup installati" (an
unmatched track still gets installed under a fallback folder name, flagged with a "da mappare" tag and a
single-dropdown "Correggi" button) and adds a "CUSTOM" option to the manual-upload Type dropdown. Both
were discussed with the user and **explicitly excluded** from this task (see Decisions below) — they
reflect either an earlier design revision or scope the user does not want ported, since the real app's
unmatched-setup semantics already changed (skip, not fallback-install) and CUSTOM was deliberately
excluded from the previous implementation pass.

The full mockup export is saved alongside this plan at `plan/HYMO Dashboard.dc.html` (decoded, real
newlines, 2376 lines) — reference it directly for exact copy/markup, do not re-derive from memory.
Relevant ranges: sidebar nav (~60-108, note the **three-group** layout: primary nav div
[setups/download/upload], then a separate `margin-top:auto` div with an `<hr>` + mapping/settings nav
items pushed to the bottom, then a third div with another divider + mode/installed-count/version footer —
this grouping differs from today's flat single-group sidebar and must be replicated); mapping tab HTML
(438-501); its delete-confirm dialog (845-859, `showMappingDeleteConfirm` — in scope; `showCorreggi` at
824-843 is NOT); translations (1163-1178 it / 1322-1337 en); state defaults (1523-1526); handlers
(1716-1739, `MAPPING_PAGE_SIZE = 8`); view-model building (2073-2097, 2345).

## Decisions locked in with the user

1. **Do not port** the mockup's Setup-installati "da mappare" tag / inline single-dropdown "Correggi"
   flow. It assumes unmatched tracks still get installed under a fallback name, which contradicts the
   real app's current skip-and-track-separately behavior. The existing end-of-run stepper dialog stays
   exactly as-is and remains the only way `manual_mapping` rows get created.
2. **Do not add** the mockup's "CUSTOM" manual-upload type. Confirmed the Upload tab's type dropdown
   (`app.js:1097-1101`) already offers only `GO`/`HYMO`, unchanged from the prior locked-in decision — no
   change needed there.
3. Scope is therefore just: one new browse+delete tab for `manual_mapping`, plus the sidebar's new
   three-group layout it needs to sit in.

## Current architecture (verified directly)

- `src/gui/web/index.html` — static shell: `<nav id="nav">` (one flat list today) + `.sidebar-footer` +
  four `<section class="view" id="view-{setups,download,upload,settings}">`.
- `src/gui/web/app.js` (~2580 lines) — single global `state`, per-view `render*View()` functions doing
  full `innerHTML` replace. `renderSidebar()` (420-475) builds one `items` array and binds clicks inline
  (checks `isSettingsDirty()` before leaving Settings, `app.js:444-448`). `goToView()` (405-416) refetches
  data on visiting `setups`/`upload`. `render()` (381-389) calls every `render*View()` + `renderModals()`.
  `renderModals()` (1872+) appends dialog HTML conditionally per `state.*Target`; the existing
  `state.deleteTarget` block (1980-2005) is the closest analog for the new mapping-delete dialog. Reusable
  as-is: `ICONS.trash`/`ICONS.warning`, `escapeHtml()`, `t()`/`tFn()`, `debounce()`, `showToast()`, and CSS
  classes `.tooltip`/`.tooltip-text`, `.toolbar`/`.search-field`/`.results-count`/`.toolbar-push-end`,
  `.btn-danger`/`.text-danger`, `.empty-state`, `.view-header`, `.tag-accent`/`.tag-accent-2`/`.tag-outline`
  — all confirmed present in `styles.css`. **`.table` does not exist anywhere in the codebase** and must be
  added.
- `src/gui/web/i18n.js` — flat `TRANSLATIONS.it/.en` (mock-derived copy) + `EXTRA.it/.en` (real-app-only
  strings), looked up via `t()`/`tFn()`.
- `src/core/settings_db.py` — `manual_mapping` table (`id` uuid PK, `type` "track"|"car", `name`,
  `matcher`, `UNIQUE(type, name)`). `get_manual_mappings(mapping_type)` (233-244) currently
  `SELECT name, matcher` — **drops `id`**, needed as the frontend's delete key. `upsert_manual_mapping`
  (247-257) is the only write path (untouched). **No delete function exists.**
- `src/processing/track_manager.py` / `car_manager.py` — `TrackManager.__init__` (line 26-32) already
  calls `self.refresh()`, which rebuilds patterns from a fresh `get_manual_mappings()` read — so **any
  newly-constructed `TrackManager()` already reflects the current DB state**, no extra `.refresh()` call
  needed on it. `CarManager` is different: `Api._get_car_manager()` (`api.py:163-167`) caches **one
  long-lived instance** across calls, so it needs an explicit `.refresh()` call after any DB change that
  affects car mappings (mirrors `Api.map_car`, `api.py:422-428`).
- `src/gui/api.py` (`class Api`) — JS↔Python bridge. `map_track`/`map_car` (410-428) are the only
  mapping-related methods today (write-only). No `list_manual_mappings`/`delete_manual_mapping`/
  `delete_all_manual_mappings` exist.

## Implementation plan

### 1. `src/core/settings_db.py`
- Extend `get_manual_mappings` to also select/return `id`:
  `SELECT id, name, matcher FROM manual_mapping WHERE type = ? ORDER BY rowid` →
  `[{"id": ..., "name": ..., "matcher": ...}, ...]`. Existing callers (`track_manager.py:51,85`,
  `car_manager.py:62`) only read `["name"]`/`["matcher"]`, unaffected by the new key.
- Add `delete_manual_mapping(mapping_id: str) -> Optional[str]`: looks up the row's `type`, deletes it,
  returns the `type` (or `None` if the id didn't match anything).
- Add `delete_all_manual_mappings(mapping_type: Optional[str] = None) -> int`: `DELETE FROM manual_mapping`
  (optionally `WHERE type = ?`), returns `cursor.rowcount`. Same `_connect()`/`with conn:` transaction style
  as `reset_to_factory_defaults` (179-191).

### 2. `src/gui/api.py`
Add a new section near `map_track`/`map_car` (its read/delete counterpart):
```python
def list_manual_mappings(self) -> list[dict[str, object]]:
    """Every manual_mapping row across both types, for the "Mappature
    manuali" tab's browse+delete table. Rows are only ever created by the
    end-of-run unmatched-setup dialog (map_track/map_car above) - this tab
    reads and deletes, never writes."""
    from core import settings_db
    tracks = [{"id": m["id"], "type": "track", "name": m["name"], "matcher": m["matcher"]}
              for m in settings_db.get_manual_mappings("track")]
    cars = [{"id": m["id"], "type": "car", "name": m["name"], "matcher": m["matcher"]}
            for m in settings_db.get_manual_mappings("car")]
    return tracks + cars

def delete_manual_mapping(self, mapping_id: str) -> dict[str, object]:
    """Deletes one manual_mapping row. If it was a car mapping, refreshes
    the cached CarManager so the deleted pattern stops matching
    immediately - TrackManager needs no equivalent call since Api never
    caches one (every TrackManager-touching method here constructs a fresh
    instance per call, which already re-reads the DB on __init__)."""
    from core import settings_db
    deleted_type = settings_db.delete_manual_mapping(mapping_id)
    if deleted_type == "car":
        self._get_car_manager().refresh()
    return {"deleted": deleted_type is not None}

def delete_all_manual_mappings(self) -> dict[str, object]:
    """Deletes every manual_mapping row (both types) - the tab's delete-all
    action, which always covers everything regardless of any active search
    filter - then refreshes the cached CarManager (see delete_manual_mapping
    for why TrackManager needs no equivalent call)."""
    from core import settings_db
    deleted_count = settings_db.delete_all_manual_mappings()
    self._get_car_manager().refresh()
    return {"deletedCount": deleted_count}
```

### 3. `src/gui/web/index.html`
- Add `<section class="view" id="view-mapping"></section>` between `view-upload` and `view-settings`.
- Split the sidebar into three groups matching the mockup:
  ```html
  <nav class="sidebar-nav" id="nav"></nav>
  <nav class="sidebar-nav sidebar-nav-bottom" id="nav-bottom"></nav>
  <div class="sidebar-footer">...</div>  <!-- unchanged contents -->
  ```
  `#nav-bottom` starts empty; its divider + two nav items are rendered by JS (labels are i18n-dependent,
  same as `#nav`'s).

### 4. `src/gui/web/app.js`
- New icon `ICONS.navMapping` (verbatim mock glyph, mock lines ~90-92).
- New state fields: `manualMappings: []`, `mappingSearch: ""`, `mappingPage: 0`, `mappingDeleteTarget: null`.
- Refactor `renderSidebar()`'s nav-building into two small helpers (avoids duplicating the click-binding
  logic, now needed for two containers): `renderNavItemsHtml(items)` and `bindNavItemClicks(containerEl)`
  (containing the existing `isSettingsDirty()`/`unsavedChangesPrompt` guard from `app.js:444-448`, verbatim).
  `renderSidebar()` then calls each helper once for `#nav` (setups/download/upload) and once for
  `#nav-bottom` (a leading `<div class="hr"></div>` + mapping/settings). `applyActiveView()` needs no
  change — its `querySelectorAll(".nav-item")` already spans both containers.
- `goToView()`: add `else if (state.view === "mapping") { refreshMappings().then(() => renderMappingView()); }`.
- `render()`: add `renderMappingView();` alongside the other `render*View()` calls.
- New `refreshMappings()`: `state.manualMappings = await api().list_manual_mappings();` — refetch
  **unconditionally on every visit** (like `refreshInstalled()`, not `ensureUploadOptions()`'s
  lazy-cache-once pattern), since the stepper can create new rows from a different tab between visits and
  this tab's entire purpose is showing current state.
- New `renderMappingView()`: client-side search/sort/paginate over `state.manualMappings` (port
  `mappingFiltered`/`mappingPageRows` from mock lines 2073-2097 — filter by name/matcher substring, sort
  track-before-car then alphabetically, 8/page via a `MAPPING_PAGE_SIZE` constant), rendering a real
  `<table class="table">` (Type/Name/Matcher/Actions columns, `tag-accent`/`tag-accent-2` type badges,
  per-row delete button using the existing `.tooltip` pattern) + `.pagination` prev/next controls, reusing
  `.toolbar`/`.search-field`/`.results-count`/`.toolbar-push-end` for the header row exactly like
  `renderSetupsView()` does. Delete-all button disabled when `manualMappings` is empty. Debounced search
  input, refocusing after re-render (mirror the existing `focusSetupsSearchInput()` pattern) since a full
  `innerHTML` replace on keystroke drops focus otherwise.
- `renderModals()`: add a `state.mappingDeleteTarget` block structurally identical to the existing
  `state.deleteTarget` block (1980-2005) — `{kind:"row",id,name}` or `{kind:"all"}` — using
  `mappingDeleteConfirmTitle/Body` / `mappingDeleteAllConfirmTitle/Body` translations. Delete-all's body
  count uses `state.manualMappings.length` (unfiltered total), matching the mock's own behavior of
  ignoring the active search filter (mock line 2095). Confirm handler calls `delete_manual_mapping(id)` or
  `delete_all_manual_mappings()`, then `refreshMappings()` + `renderMappingView()` + `showToast(...)`.

### 5. `src/gui/web/i18n.js`
- Add `navMapping: "Associazioni manuali"` / `"Manual associations"` to the existing combined nav-label
  line in both `TRANSLATIONS.it`/`.en`.
- Add a new key block to both blocks, copied verbatim from the mock (lines 1163-1178 it / 1322-1337 en):
  `mappingTitle`, `mappingDesc`, `mappingColType/Name/Matcher/Actions`, `mappingTypeTrack/Car`,
  `mappingResultsWord`, `mappingSearchPlaceholder`, `mappingEmptyText`, `mappingDeleteAllButton`,
  `mappingDeleteConfirmTitle/Body`, `mappingDeleteAllConfirmTitle/Body`, `mappingDeletedToast`,
  `mappingDeletedAllToast`, `mappingPrevPage/NextPage`, `mappingPageLabel`. No `EXTRA` additions needed —
  the dialog reuses the already-existing `deleteConfirmCancel`/`deleteConfirmConfirm`.

### 6. `src/gui/web/styles.css`
- Add `.table`/`.table th`/`.table td`/row-hover styling (new — genuinely absent today) plus
  `.mapping-matcher` (monospace matcher column) and `.mapping-actions-col` (right-aligned actions column),
  built from existing tokens only.
- Add a generic `.pagination`/`.pagination-label` (reusable by any future paginated list).
- Sidebar: add `.sidebar-nav-bottom { margin-top: auto; }` and extend the existing (currently unused)
  `.sidebar-footer .hr` rule to also cover `.sidebar-nav-bottom .hr`; remove `margin-top: auto` from
  `.sidebar-footer` (line 334) since `.sidebar-nav-bottom` is now the element pushed to the bottom — no
  visual regression, the same `.sidebar` gap already separates the groups.

### 7. Tests
- `tests/unit/test_settings_db.py`: fix `test_upsert_manual_mapping_creates_new_entry` and
  `test_manual_mappings_are_isolated_by_type` (both do full-dict `==` without `id`, will break once `id`
  is added — assert on `name`/`matcher` fields instead). Add: `test_get_manual_mappings_includes_id`,
  `test_delete_manual_mapping_removes_row_and_returns_type`,
  `test_delete_manual_mapping_returns_none_for_unknown_id`,
  `test_delete_manual_mapping_only_removes_targeted_row`,
  `test_delete_all_manual_mappings_removes_everything_and_returns_count`,
  `test_delete_all_manual_mappings_filters_by_type`.
- `tests/unit/test_gui_api.py` (near `test_map_track_updates_and_refreshes`/`test_map_car_updates_and_refreshes`):
  `test_list_manual_mappings_combines_both_types`,
  `test_delete_manual_mapping_refreshes_car_manager_when_type_car`,
  `test_delete_manual_mapping_does_not_touch_car_manager_when_type_track`,
  `test_delete_manual_mapping_handles_missing_id`,
  `test_delete_all_manual_mappings_refreshes_car_manager`.
- No JS test suite exists in this repo — frontend changes have no automated test counterpart, consistent
  with the rest of `app.js`.

## Verification

- `pytest` (full suite, plus the new/modified tests above).
- Run `python src/main.py --sandbox`, navigate to the new "Mappature manuali" tab: confirm it's empty
  initially, then use the existing end-of-run unmatched-setup stepper (or directly call
  `map_track`/`map_car` via a sandboxed run with intentionally-unmatched fixture data) to create a couple
  of rows, revisit the tab, and confirm they appear with correct type tags. Exercise search, pagination
  (create >8 rows), per-row delete, and delete-all, confirming toasts and that deleted rows actually stop
  matching (e.g. a deleted car mapping's setup goes back to unmatched on the next sandboxed run).
  Confirm the sidebar's new three-group layout renders correctly and Settings' unsaved-changes nav guard
  still fires when leaving Settings for any tab, including the new Mapping tab.
