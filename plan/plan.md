# GO Setups support (slave mode) + unified Dropbox car/track layout

## Context

HYMO (this app) currently syncs LMU setups from TrackTitan in `full`/`master` modes and installs them from a Dropbox share in `slave` mode. We're adding a second, independent setup provider: **GO Setups**, published outside this app — Matte uploads GO archives to Dropbox by hand — so only `slave` mode gains new behavior for them.

A GO archive is a zip whose name starts with `GO` (e.g. `GO-ORECA-07-ELMS-IMOLA.zip`, see the extracted example at `C:\Users\matte\Downloads\esempio_go_setups\GO-ORECA-07-ELMS-IMOLA\`). Inside, files sit under a track subfolder and include both `.svm` setup files and MoTeC telemetry pairs (`.ld`/`.ldx`) whose names embed a GO version string that changes release to release — so two versions of "the same" archive share no internal filenames in common. Telemetry files must be treated exactly like setups: copied in, cleaned up when a new version replaces them.

There's no reliable "has this changed" signal for GO archives, so every slave run unconditionally re-downloads, re-extracts and re-installs every one found. To still delete old-version files despite ever-changing internal names, the app remembers what it last installed for a given archive (reusing the existing DB machinery) and diffs against that on each run — same mechanism the TrackTitan flow already uses.

Car/track recognition for GO relies **exclusively on a hand-maintained Dropbox folder structure**, never on parsing the archive name (which is ambiguous — "ORECA-07-ELMS-IMOLA" doesn't cleanly split into car vs. track).

**Design change made after the first pass of this plan:** Matte decided the Dropbox layout itself should unify — both HYMO's own auto-published setups and manually-uploaded GO archives live under the *same* `<Car>/<Track>/` tree, not a separate `GO/` subtree. This means `MasterManager`'s publish path changes too (today it publishes flat, one folder per car only), and any setups it already published under the old layout must be relocated automatically the next time MASTER runs — confirmed with Matte: automatic and silent, no user action required. Local LMU installation is **unaffected** by any of this — it stays exactly as it is today (one folder per track, no car level); only the Dropbox share layout changes.

## Design decisions locked in with the user

1. Recognition: a zip is a GO archive if its filename starts with `GO` (case-insensitive).
2. **Unified Dropbox layout**: `<DROPBOX_FOLDER>/<Car>/<Track>/<file.zip>` for both HYMO-published zips (`HYMO-{track}_{car}_{id}_{ts}.zip`) and GO zips (`GO-*.zip`, whatever the archive's own name is) — no separate `GO/` root. Depth is exactly 3 segments under `DROPBOX_FOLDER`. Reuses the existing Dropbox credentials/folder setting — no new settings.
3. `<Track>` (for GO) is resolved through the *same* `TrackManager`/`config/tracks.json` mapping (+ per-user "Correggi" overrides) TrackTitan setups already use, so GO setups land in the same physical LMU track folder. `<Car>` is used verbatim (no car-name-mapping mechanism exists anywhere in this codebase — TrackTitan car names are already trusted as-is, same policy applies to the GO Dropbox car-folder name).
4. **Fallback folder naming is source-specific**: when a track can't be mapped, TrackTitan/HYMO setups still land in `<Track>-HYMO` (unchanged), but GO setups land in `<Track>-GO` instead — so unmapped setups from each source stay distinguishable at a glance.
5. No version/update detection for GO this phase — always reinstall every GO archive, every slave run.
6. Because internal filenames change every version, the app keeps a minimal local record (reusing `installed_setups`) of what a GO archive last installed, purely to delete stale files next run.
7. `.ld`/`.ldx` are extracted and installed exactly like `.svm` for GO archives specifically — must not change the global `SETUP_FILE_EXTENSIONS` behavior used by the regular TrackTitan flow.
8. GO-installed setups appear in the existing "Setup installati" tab with a small "GO" badge.
9. **Dropbox migration**: HYMO zips already published under the old `<Car>/<file.zip>` layout are relocated (server-side move, not re-uploaded) to the new `<Car>/<Track>/<file.zip>` layout automatically on the next MASTER run, with no user-visible action needed.

## Implementation

### 1. `src/domain/setup.py` — unify HYMO's own share layout

- `remote_relative_path`: change from `f"{self.safe_car}/{self.remote_filename}"` to `f"{self.safe_car}/{self.safe_track}/{self.remote_filename}"`. Update the comment: the share is now organized by car *then* track for both HYMO and GO Setups, so a human browsing Dropbox finds a given car+track's setups from either source in one place.
- No other change — `remote_filename`/`_REMOTE_NAME_RE`/`parse_remote_zip_name` stay filename-only and depth-agnostic, so they keep recognizing HYMO zips regardless of which layout (old or new) they currently sit under.

### 2. `src/domain/go_setup.py` (new)

- `looks_like_go_name(name: str) -> bool` — cheap prefix check, `name.lower().startswith("go")`. Used by both Dropbox clients as an early, silent filter: "not even worth considering as a GO candidate" (e.g. a legacy-layout HYMO zip, or any unrelated file) vs. "looks like it was meant to be a GO archive but is malformed" (worth a warning).
- `is_go_zip_name(name: str) -> bool` — `looks_like_go_name(name) and name.lower().endswith(".zip")`.
- `_sanitize_id_component(value: str) -> str` — replace `\ / : * ? " < > |` and whitespace runs with `_`, strip, cap length, fall back to `"unknown"` if empty.
- `build_go_setup_id(car: str, track: str, zip_stem: str) -> str` — stable synthetic id: `f"go-{sanitized_readable}-{sha1_hex10}"`, the SHA1 suffix (10 hex chars) computed over `car`, `track`, `zip_stem` joined with `"\x00"` (disambiguates two different triples that sanitize to the same readable text). The `"go-"` prefix makes collision with a real TrackTitan UUID structurally impossible (UUIDs never start with `g`/`o`).
  - Tradeoff to document in the README: this id is stable only as long as the *zip filename* stays the same across a version bump (matches the real GO workflow — the zip is named for the car/track combo, only files *inside* carry the version). If the zip is ever renamed, the old id's row is orphaned (removable via the existing "Delete setup" GUI action).
- `@dataclass class RemoteGoSetup` (unfrozen, matches `RemoteSetup`'s style): `name`, `path_lower`, `car`, `track`, `setup_id`.
- `parse_go_entry(name: str, path_lower: str, relative_segments: list[str]) -> Optional[RemoteGoSetup]` — shared validator: requires exactly 3 segments and `is_go_zip_name(name)`; on success returns a populated `RemoteGoSetup` (car/track verbatim from segments 0/1, id via `build_go_setup_id`); else `None`.

### 3. `src/core/config.py`

Add near `SETUP_FILE_EXTENSIONS`:
```python
GO_SETUP_FILE_EXTENSIONS: set[str] = {".svm", ".ld", ".ldx"}
```
Hardcoded, **independent** of `SETUP_FILE_EXTENSIONS` (which is user-editable and governs the regular TrackTitan flow only).

### 4. `src/clients/protocols.py`

Add to `DropboxClientProtocol`:
- `def list_go_setups(self) -> list[RemoteGoSetup]: ...`
- `def remote_path(self, relative_path: str) -> str: ...` — the fully-qualified path a given share-relative path would live at (what `upload()` already computes internally today; pulled out so `MasterManager` can compute an *expected* path without performing an upload).
- `def move(self, from_path: str, to_path: str) -> None: ...` — server-side rename/relocate.

### 5. `src/clients/dropbox_client.py`

- Add `remote_path(self, relative_path: str) -> str: return f"{self.folder}/{relative_path}"`; refactor `upload()` to call it (`remote_path = self.remote_path(remote_name)`) instead of duplicating the f-string.
- Add `move(self, from_path: str, to_path: str) -> None`: `self._call(self.dbx.files_move_v2, from_path, to_path, autorename=False)`, log info. Let a genuine SDK error propagate (mirrors `delete`); the caller (MasterManager) catches broadly since a failed relocate must not abort the run.
- `list_setups()` — right before the existing "non-conforming" warning, add: `if is_go_zip_name(name): continue` (silent skip — GO archives are a recognized, expected coexisting file type now, not stray files).
- New `list_go_setups(self) -> list[RemoteGoSetup]`:
  - iterate `self._list_all_entries()` (existing, unscoped — the GO tree is no longer a separate subfolder, it's the same tree `list_setups()` scans).
  - for each entry, first check `name` present and `looks_like_go_name(name)` — if not, `continue` silently (this is what keeps a legacy-layout HYMO zip, or any unrelated file, from ever producing a spurious "non-conforming GO entry" warning here).
  - require `path_lower`/`path_display` present; **use `path_display` (not `path_lower`) to derive car/track** — Dropbox's SDK always lowercases `path_lower`, and decision #3 requires the car name verbatim.
  - slice `path_display` into segments *after* `self.folder`'s depth (segment-count based, not character-offset, so casing differences between the configured folder and Dropbox's stored casing never matter).
  - call `parse_go_entry(name, path_lower, segments)`; `None` → `log.warning(f"Ignoring non-conforming GO Setup entry on share: {path_display}")` + skip; else append.

### 6. `src/clients/mocks/mock_dropbox_client.py`

- Add `remote_path(self, relative_path: str) -> str: return str((self.folder / relative_path).resolve())`; refactor `upload()` to use it.
- Add `move(self, from_path: str, to_path: str) -> None`: `dst = Path(to_path); dst.parent.mkdir(parents=True, exist_ok=True); shutil.move(str(Path(from_path)), str(dst))`, log info.
- `list_setups()` — skip (no warning) any entry whose name satisfies `is_go_zip_name`.
- New `list_go_setups(self) -> list[RemoteGoSetup]`: iterate `sorted(self.folder.glob("**/*.zip"))`; skip silently if not `looks_like_go_name(entry.name)`; else `segments = list(entry.relative_to(self.folder).parts)`, call `parse_go_entry(entry.name, str(entry.resolve()), segments)`, warn+skip on `None`, else append.

### 7. `src/orchestration/master_manager.py` — relocate legacy-layout setups

In `_dispatch`, the existing "already up to date" branch currently does:
```python
existing: Optional[RemoteSetup] = remote.get(setup.id)
if existing and existing.ts >= setup.last_updated:
    log.info("Already up to date on share. Skipping.")
    return
```
Since `existing.ts >= setup.last_updated` already guarantees the filename/content are current (the timestamp is embedded in and parsed back out of the filename), the only thing that can still be "wrong" here is *where* the file sits. Replace with:
```python
existing: Optional[RemoteSetup] = remote.get(setup.id)
if existing and existing.ts >= setup.last_updated:
    self._relocate_if_stale_path(setup, existing)
    return
```
New method:
```python
def _relocate_if_stale_path(self, setup: Setup, existing: RemoteSetup) -> None:
    target_path = self.dropbox_client.remote_path(setup.remote_relative_path)
    if existing.path_lower.lower() == target_path.lower():
        log.info("Already up to date on share. Skipping.")
        return
    try:
        self.dropbox_client.move(existing.path_lower, target_path)
        log.info(f"Relocated {setup.id} to the unified car/track layout: {target_path}")
    except Exception as e:
        log.error(f"Failed to relocate {setup.id} to {target_path}: {e}")
```
Runs synchronously on the producer thread (not dispatched to the worker pool) — a Dropbox move is a cheap metadata-only server call, unlike a real publish (download+repackage+upload), so no need for the pool/semaphore machinery here. No new `ProgressEvent` kind — relocations are logged only, kept out of the GUI activity feed since they're an invisible one-time reorg, not a new setup being published.

Everything else in `master_manager.py` (the real-publish/delete-old-version path in `_publish`) is unaffected: when a setup's content genuinely changed, it already re-uploads to `setup.remote_relative_path` (now correctly nested) and deletes whatever `existing.path_lower` was — format-agnostic, so it already cleans up a legacy-layout file for free whenever that setup happens to get a real update.

### 8. `src/processing/setup_manager.py`

- `_calculate_setup_installation_dir(self, track: str, fallback_suffix: str = "HYMO") -> tuple[Path, bool, Optional[str]]`: replace the hardcoded `f"{track}-HYMO"` with `f"{track}-{fallback_suffix}"`; update the log line similarly. Existing callers (`install_setup`'s default, `_try_relocate_setup`) keep today's behavior unchanged since they don't pass the new parameter (`_try_relocate_setup` never reaches the fallback branch anyway — it only proceeds once `track_found` is `True`).
- `install_setup(self, downloaded_path, setup, extensions: Optional[set[str]] = None, source: str = "tracktitan", fallback_suffix: str = "HYMO") -> None`:
  - pass `extensions` through to `_copy_file_to_lmu`.
  - pass `fallback_suffix` through to `_calculate_setup_installation_dir(setup.track, fallback_suffix)`.
  - change the cleanup gate from `if DELETE_PREVIOUS_VERSION:` to `if DELETE_PREVIOUS_VERSION or source == "go":` — decision #6 requires GO cleanup unconditionally, independent of that (TrackTitan-oriented) user toggle.
  - pass `source=source` to `self.database.add_installed_setup(...)`.
- `_copy_file_to_lmu(self, extraction_path, setup_installation_dir, extensions: Optional[set[str]] = None) -> list[Path]`: resolve `exts = extensions if extensions is not None else SETUP_FILE_EXTENSIONS` inside the method body (matches this class's existing pattern of resolving config-backed defaults at call time, keeps `mocker.patch(".../SETUP_FILE_EXTENSIONS", ...)` working).
- No changes needed to `update_tracks_not_found`/`_try_relocate_setup`/`delete_setup` — already fully generic over `Setup`/`InstalledSetup`, work unmodified for GO rows.

### 9. `src/domain/setup_db.py`

- Add `source TEXT NOT NULL DEFAULT 'tracktitan'` to the base `CREATE TABLE IF NOT EXISTS` (13th column) and as a new "Migration 4" `ALTER TABLE installed_setups ADD COLUMN source TEXT NOT NULL DEFAULT 'tracktitan'` (same try/except pattern as the other three migrations — SQLite backfills existing rows via the default).
- `InstalledSetup`: append `source: str`; `from_row` reads `source=row[12]`.
- `add_installed_setup(..., source: str = "tracktitan")`: add to INSERT columns/values and `ON CONFLICT ... DO UPDATE SET source = excluded.source`.
- `update_installed_setup(setup: InstalledSetup)`: add `source = ?` / `setup.source` so `_try_relocate_setup`'s read-then-write round trip doesn't silently drop it.

### 10. `src/orchestration/slave_manager.py`

- Imports: `RemoteGoSetup` from `domain.go_setup`, `GO_SETUP_FILE_EXTENSIONS` from `core.config`, stdlib `time`.
- `run()`: after the existing `for remote in self.dropbox_client.list_setups(): ...` loop and before the `FINISH` emit, add a second loop over `self.dropbox_client.list_go_setups()` with the identical cancel-check → `_emit(STOPPED)` → `return` guard, calling `self._process_go(remote)` per item.
- New `_process_go(self, remote: RemoteGoSetup) -> None`:
  - log id/car/track/filename; `_emit(ProgressEvent(START, remote.name))`.
  - `local_zip = Path(DOWNLOAD_PATH) / f"{remote.setup_id}.zip"` (the synthetic id, not `remote.name` — two different car/track folders could legally contain a same-named zip); `dropbox_client.download_to(remote.path_lower, local_zip)`.
  - build a synthetic TrackTitan-API-shaped dict: `id=remote.setup_id`, `title=f"{remote.car} - {remote.track} (GO)"`, `setupCombos=[{"car": {"name": remote.car}, "track": {"name": remote.track}}]`, `hotlapLink=None`, `lastUpdatedAt=int(time.time()*1000)` (purely informational), `isBundle=False`. Wrap in `Setup(...)`.
  - **No `is_installed_last_version` pre-check** — unconditionally call `self.setup_manager.install_setup(local_zip, setup, extensions=GO_SETUP_FILE_EXTENSIONS, source="go", fallback_suffix="GO")`.
  - `_emit(ProgressEvent(INSTALL, remote.name))`.
- Update the class docstring to mention GO Setups.

### 11. `src/gui/api.py`

`_serialize_installed`: add `"source": setup.source` to the returned dict. Nothing else needs to change — grouping, delete, `map_track`, bootstrap counts are all already generic over `InstalledSetup`.

### 12. `src/gui/web/app.js`

In `renderCarRow`, add a badge when `s.source === "go"`, using the app's existing tooltip component (`.tooltip`/`.tooltip-text`) and the existing `tag-accent-2` CSS class (already defined in `styles.css`, currently unused — no CSS changes needed):
```js
${s.source === "go" ? `<span class="tooltip"><span class="tag tag-accent-2">GO</span><span class="tooltip-text">${escapeHtml(t("goBadgeTooltip"))}</span></span>` : ""}
```
Scoped to the per-setup row, not the track-group header.

### 13. `src/gui/web/i18n.js`

Add `goBadgeTooltip` to `EXTRA.it` (`"Setup GO (provider di terze parti)"`) and `EXTRA.en` (`"GO Setup (third-party provider)"`). The "GO" badge text itself stays untranslated, same treatment as "HYMO".

### Verified as needing no changes
- `src/main.py` (`run_slave` already wires `SlaveManager` generically).
- `gui/api.py`'s `_HOT_RELOAD_MODULES` (already includes `clients.dropbox_client`, `orchestration.slave_manager`, `orchestration.master_manager`, `processing.setup_manager`).
- No new Settings fields — GO reuses the existing Dropbox credentials/folder entirely.

## Tests

**Unit — new `tests/unit/test_go_setup.py`**: `looks_like_go_name`/`is_go_zip_name` case-insensitivity and non-zip handling; `build_go_setup_id` determinism, `"go-"` prefix, filesystem-safety, disambiguation of two triples that sanitize to the same text; `parse_go_entry` valid case + wrong segment counts (1/2/4) + right depth but non-"GO" name + right depth but non-.zip.

**Unit — `tests/unit/test_setup.py`** (extend/fix): **required update** — `test_remote_relative_path_nests_under_car` currently asserts `"Ferrari_499P/HYMO-....zip"`; update to `"Ferrari_499P/Le_Mans_Bugatti/HYMO-....zip"` (car then track then filename).

**Unit — `tests/unit/test_dropbox_client.py`** (extend): update the `_entry()` helper to also accept/set `path_display` (default = `path_lower` unless overridden, so existing tests keep passing). New: `remote_path()` builds `f"{folder}/{relative}"`; `move()` calls `dbx.files_move_v2(from_path, to_path, autorename=False)`; `list_go_setups()` parses car/track from `path_display` preserving case even though `path_lower` is lowercased, skips+warns wrong depth (2 or 4 segments) *for a "GO"-prefixed name*, skips **silently** a non-"GO"-prefixed entry regardless of depth (proves legacy HYMO zips never trigger a GO warning), ignores non-.zip, paginates, not-found folder → empty list, `AuthError` propagates. Plus a regression test: `list_setups()` silently skips a "GO"-prefixed zip (no "non-conforming" warning) at any depth.

**Unit — `tests/unit/test_mock_dropbox_client.py`** (extend): mirrors the above against the local-folder mock; `remote_path()`/`move()` round-trip via a real temp dir; `list_setups()` ignoring any `GO*.zip` without warning regardless of depth.

**Unit — `tests/unit/test_setup_manager.py`** (extend): `_copy_file_to_lmu` honors an explicit `extensions` override, defaults to `SETUP_FILE_EXTENSIONS` when omitted; `install_setup` threads `extensions`/`source`/`fallback_suffix` through; `_calculate_setup_installation_dir(track, fallback_suffix="GO")` on an unmapped track returns a path containing `"-GO"` (and not `"-HYMO"`), companion test confirms the default (`"HYMO"`) is unchanged; `install_setup` records `source` (default `"tracktitan"`, explicit `"go"`); **`install_setup(..., source="go")` still runs `_cleanup_old` and removes a stale file even with `DELETE_PREVIOUS_VERSION` patched to `False`**, with a companion test proving `source="tracktitan"` behavior is unchanged under the same toggle.

**Unit — `tests/unit/test_setup_db.py`** (extend): `source` defaults/round-trips through `add_installed_setup`/`update_installed_setup`; a real-file migration test (open a temp *file* DB with the old 12-column schema, insert a row, reopen via `SetupDb()`, assert `source == "tracktitan"` on the pre-existing row). **Required fix**: `test_installed_setup_from_row`'s hand-built 12-element row tuple needs a 13th element + a `source` assertion, or it `IndexError`s once `from_row` reads `row[12]`.

**Unit — `tests/unit/test_slave_manager.py`** (extend): **required fix first** — the `sm` fixture's `dbx = MagicMock()` needs `dbx.list_go_setups.return_value = []`, or the 5 existing tests calling `manager.run()` break (`MagicMock()` isn't iterable). New: `_process_go` downloads to `DOWNLOAD_PATH/{setup_id}.zip`; builds the right `Setup`; calls `install_setup` once with `extensions=GO_SETUP_FILE_EXTENSIONS, source="go", fallback_suffix="GO"`; never calls `is_installed_last_version`; `run()` processes a regular remote then a GO remote in one pass ending in one `FINISH`; cancel right after the regular loop still stops before the GO loop starts.

**Unit — `tests/unit/test_master_manager.py`** (extend): **required fixture update** — add `dbx.remote_path.side_effect = lambda rel: f"/lmu-setups/{rel}"` to the `mm` fixture (a realistic default so path-comparison tests behave meaningfully instead of comparing `MagicMock` instances). **Required test fix** — `test_skip_when_up_to_date` currently builds `_remote("HYMO-Spa_Porsche_963_id1_1000.zip", "id1", 1000)` whose `path_lower` is flat (`/lmu-setups/hymo-...zip`), which under the new logic no longer matches the nested target path and would trigger a relocate instead of a pure no-op; update this test's `_remote(...)` call to use the fully-nested path (`"Porsche_963/Spa/HYMO-Spa_Porsche_963_id1_1000.zip"`, matching `path_lower`) so it keeps testing a *true* no-op skip (assert `dbx.move` also not called). New: `test_relocates_legacy_flat_layout_without_republishing` — `existing` at the old flat `<car>/<file>.zip` path with a current timestamp → `dbx.move` called once with `(existing.path_lower, "/lmu-setups/Porsche_963/Spa/HYMO-...zip")`, `dm.download`/`dbx.upload`/`dbx.delete` all NOT called; a companion test where `dbx.move` raises → the run completes without raising (error logged, not propagated) and other setups in the same run still get processed.

**Unit — `tests/unit/test_config.py`** (extend): `GO_SETUP_FILE_EXTENSIONS == {".svm", ".ld", ".ldx"}`, distinct from `SETUP_FILE_EXTENSIONS`.

**Unit — `tests/unit/test_gui_api.py`** (extend): **required fix first** — `_fake_installed()`'s base dict needs `source="tracktitan"` added or existing tests using it `AttributeError`. New: serialization includes `source` for both values.

**Integration — `tests/integration/sandbox_harness.py`** (extend): add `Sandbox.add_go_zip(car: str, track: str, zip_name: str, members: dict[str, str]) -> Path` writing to `self.share / car / track / zip_name` (no `GO/` marker level — mirrors the unified layout). `run_master()`/`run_slave()` need no changes.

**Integration — new `tests/integration/test_sandbox_go_setups.py`**:
- install a GO archive (svm + ld/ldx pair, matching the real example's shape) and assert all files land in the mapped LMU track folder with `source == "go"` in the DB.
- **key test**: publish v1, run slave, overwrite the *same* Dropbox zip path with v2 content under *different* internal filenames (no version signal anywhere), run slave again — assert v1's file is gone and only v2 remains (proves decisions #5+#6 together).
- a regular TrackTitan setup and a GO archive for the same track both land in the same physical LMU folder (proves decision #3's mapping reuse).
- a GO archive whose track folder matches nothing in `tracks.json` lands under `<Track>-GO` (not `-HYMO`) — proves decision #4.
- stray zip at wrong depth is skipped+warned, installs nothing; correctly-nested non-"GO" zip is skipped+warned; a GO zip is never picked up by `list_setups()`.

**Integration — extend `tests/integration/test_sandbox_updates.py`** (or a new file alongside it): publish a setup via `run_master()` under the (simulated) *old* flat layout — write the zip directly via the harness at `share / car / filename.zip` bypassing normal publish — then run `run_master()` again with the same TrackTitan catalog (nothing changed) and assert the file is now at `share / car / track / filename.zip`, the old path is gone, and no TrackTitan download happened for it (spy on `MockTrackTitanClient` or on `DownloadManager.download`).

**Manual verification**: `python src/main.py --mock-tracktitan --mock-lmu --mode master` then `--mode slave` to see a full publish→relocate→install cycle; hand-create `sandbox/dropbox/<Car>/<Track>/GO-Something.zip` (svm+ld+ldx members) and rerun `--mode slave` to exercise the GO path end to end. Run the full existing suite (`pytest`) to confirm nothing regresses. Smoke-test the GUI's "Setup installati" tab against a sandbox slave run to confirm the GO badge renders.

## Documentation

Add a short "GO Setups" subsection to `readme.md`/`readme.it.md` (after "Modes in detail", before "Track mapping"): what GO is, that both HYMO's own published setups and manually-uploaded GO archives now share one Dropbox tree — `<Dropbox folder>/<Car>/<Track>/` — so browsing Dropbox shows everything for a car/track together; that GO archives are uploaded by hand into the matching `<Car>/<Track>/` folder (no new credentials); that Install-only mode picks GO up automatically; that telemetry files are intentionally installed alongside setups; that GO setups are always reinstalled every run (expected, not a bug); that an unmapped GO track lands under `<Track> - GO` (vs. `<Track> - HYMO` for regular setups); that they show up with a "GO" badge; and the operational caveat — **keep the same zip filename across GO version updates**, renaming starts a fresh, unrelated install record. Mention that upgrading to this version triggers a one-time, automatic relocation of already-published setups into the new layout on the next Upload-only run — no action needed, may take a moment the first time. Add the manual sandbox-testing recipe to the Sandbox section.
