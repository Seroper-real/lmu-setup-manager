// HYMO Dashboard frontend. Vanilla JS, no framework, no build step.
// Full-innerHTML replace per render() call, per view. window.pywebview.api.* is
// the only bridge into Python; window.onProgress is Python's push channel back.

const state = {
  view: "setups",
  language: "it",
  bootstrap: null,
  selectedMode: "full",
  // Independent per-section visibility toggles (replacing a single global
  // show/hide) so revealing TrackTitan tokens doesn't also reveal Dropbox
  // credentials and vice versa.
  showTokenSecrets: false,
  showDropboxSecrets: false,
  advancedOpen: false,
  running: false,
  runStatus: "idle", // idle | running | completed | stopped | error
  activity: [],
  installedSearch: "",
  installedData: { groups: [], totalCount: 0, grandTotal: 0 },
  // "Mappature manuali" tab: browse+delete view over manual_mapping rows
  // created exclusively by the end-of-run unmatched-setup dialog below
  // (map_track/map_car) - refetched unconditionally on every tab visit.
  manualMappings: [],
  mappingSearch: "",
  mappingPage: 0,
  // { kind: "row", id, name } | { kind: "all" } | null.
  mappingDeleteTarget: null,
  // Track cards default to collapsed (perf: >400 setups rendered fully expanded
  // was the main source of startup jank) and open on user click; the Set holds
  // manually-expanded track keys. A non-empty search force-expands every card
  // regardless of this set, without mutating it, so clearing the search restores
  // the manual state exactly as the user left it.
  expandedTracks: new Set(),
  // Per-car accordion inside an expanded track card, keyed by `${track}::${car}` -
  // reveals that car's HYMO and/or GO sub-groups on click.
  expandedCarGroups: new Set(),
  // Per-installed-setup accordion inside an expanded car/type group, keyed by
  // setupId - reveals that one installed setup's individual file names on click.
  expandedCars: new Set(),
  trackFolderOptions: [],
  // Lazy-fetched once (like trackFolderOptions above), for the Upload tab's
  // car dropdown.
  uploadCarOptions: [],
  // { filePath, fileName, type, track, car } once a zip is picked on the
  // Upload tab, else null (dropzone shown instead of the assignment form).
  manualUpload: null,
  // Which of the Upload tab's searchable dropdowns ("track" | "car") is
  // currently open, plus each one's own in-progress search text - both reset
  // whenever the panel closes or a value is picked.
  uploadOpenDropdown: null,
  uploadDropdownSearch: {},
  // Keyboard-arrow highlight index into the currently filtered option list,
  // keyed by dropdown id ("track" | "car") - reset to 0 whenever a dropdown
  // opens or its search text changes.
  uploadDropdownHighlight: {},
  // End-of-run "unmatched setups" dialog (see window.onProgress). Holds
  // { items: [{ kind: "track" | "car", name, selected }] } - one entry per
  // distinct unmatched track/car value (never a full setup, and never both a
  // track and a car in the same entry), populated from the {tracks, cars}
  // payload by openUnmatchedModal(), else null.
  unmatchedTarget: null,
  deleteTarget: null,
  // Settings > Danger Zone confirm/busy dialog. { kind: "dropbox" | "factory" }
  // while open, else null. dangerCountdown gates the confirm button (ticks down
  // from 5 via _dangerTimer); dangerBusy swaps the dialog into a blocking
  // spinner for the duration of the actual API call.
  dangerTarget: null,
  dangerCountdown: 0,
  dangerBusy: false,
  // Live count of Dropbox setups deleted so far during the "dropbox" danger
  // action, pushed from Python via window.onDangerProgress - reset to 0
  // whenever that action starts.
  dangerDeletedCount: 0,
  // "deleting" while zips are being removed (dangerDeletedCount is
  // meaningful), "cleaning_folders" during the trailing empty-folder prune
  // that has no per-item count of its own - see window.onDangerProgress.
  dangerPhase: "deleting",
  dropboxOAuth: null,
  tracktitanFetch: null,
  validationErrors: null,
  authErrorCode: null,
  authErrorStatus: null,
  showWarning: false,
  settingsForm: null,
  // JSON snapshot of settingsForm as of the last successful save/load, used to
  // detect unsaved edits now that there is no manual Save button.
  settingsSavedSnapshot: null,
  // { reason: "nav", target } | { reason: "close" } | null - set when the user
  // tries to leave Settings (or close the app) with unsaved edits pending.
  unsavedChangesPrompt: null,
};

// Interval handle backing state.dangerCountdown - module-level rather than on
// `state` itself since it's a live timer handle, not renderable data.
let _dangerTimer = null;

// ----- helpers --------------------------------------------------------------

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Icons, ported verbatim (viewBox/paths) from the real Claude Design mock
// ("HYMO Dashboard.dc.html") so the running app matches it icon-for-icon
// instead of using emoji/Unicode stand-ins. `error` has no mock equivalent
// (its fake activity feed never produces that state) - it reuses the
// validation dialog's circle-exclamation shape, themed via currentColor.
const ICONS = {
  logo: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17l4-9 4 6 3-4 5 7"></path></svg>`,
  navSetups: `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4" width="17" height="16" rx="2"></rect><path d="M8 2.5v3M16 2.5v3M3.5 9.5h17"></path></svg>`,
  navDownload: `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5v11M8 11l4 4 4-4"></path><path d="M4.5 16v2.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V16"></path></svg>`,
  navUpload: `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 17.5v-11M8 10l4-4 4 4"></path><path d="M4.5 16v2.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V16"></path></svg>`,
  navMapping: `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h11M11 5l3 3-3 3"></path><path d="M20 16H9M13 13l-3 3 3 3"></path></svg>`,
  uploadCloud: `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-neutral-500)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18a4.5 4.5 0 0 1-.5-8.97A5.5 5.5 0 0 1 17.3 8.1 4 4 0 0 1 17 16"></path><path d="M12 12v6.5M9.5 14.5 12 12l2.5 2.5"></path></svg>`,
  navSettings: `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"></circle><path d="M12 3.5v2.4M12 18.1v2.4M4.9 6.3l1.7 1.7M17.4 16l1.7 1.7M3.5 12H6M18 12h2.5M4.9 17.7l1.7-1.7M17.4 8l1.7-1.7"></path></svg>`,
  search: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-neutral-500)" stroke-width="2" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="M20 20l-4.35-4.35"></path></svg>`,
  chevron: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"></path></svg>`,
  folder: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"></path></svg>`,
  folderBrowse: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"></path></svg>`,
  hotlap: `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.6A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8ZM9.6 15.5v-7l6.3 3.5-6.3 3.5Z"></path></svg>`,
  eyeOpen: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12s3.5-7 9-7 9 7 9 7-3.5 7-9 7-9-7-9-7Z"></path><circle cx="12" cy="12" r="2.6"></circle></svg>`,
  eyeClosed: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18M10.6 10.7a2.6 2.6 0 0 0 3.6 3.6M6.6 6.7C4.5 8 3 12 3 12s3.5 7 9 7c1.6 0 3-.5 4.2-1.2M9.9 5.2A9.8 9.8 0 0 1 12 5c5.5 0 9 7 9 7a13.7 13.7 0 0 1-2.4 3.3"></path></svg>`,
  externalLink: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"></path><path d="M14 4h6v6"></path><path d="M10 14 20 4"></path></svg>`,
  info: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><line x1="12" y1="11" x2="12" y2="16.5"></line><circle cx="12" cy="7.6" r="0.4" fill="currentColor"></circle></svg>`,
  trash: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"></path><path d="M9 7V4h6v3"></path><path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"></path></svg>`,
  copy: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="13" height="13" rx="2"></rect><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path></svg>`,
  play: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4.5v15l13-7.5Z"></path></svg>`,
  stop: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>`,
  activityStopped: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"></circle><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"></path></svg>`,
  activityError: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 7.5v6"></path><circle cx="12" cy="16.7" r="0.6" fill="currentColor"></circle></svg>`,
  activityInstalled: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M8 12.3l2.6 2.6L16 9.3"></path></svg>`,
  warning: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-300)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 22 20.5H2Z"></path><path d="M12 10v4.5"></path><circle cx="12" cy="17.5" r="0.6" fill="var(--color-accent-300)"></circle></svg>`,
  fieldWarning: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-warning)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 22 20.5H2Z"></path><path d="M12 10v4.5"></path><circle cx="12" cy="17.5" r="0.6" fill="var(--color-warning)"></circle></svg>`,
  validation: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-300)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 7.5v6"></path><circle cx="12" cy="16.7" r="0.6" fill="var(--color-accent-300)"></circle></svg>`,
};

// Flat lookup against the mock's own TRANSLATIONS, falling back to EXTRA for
// the handful of real-app states the mock's fixed fixture data never covered.
function t(key) {
  const dict = TRANSLATIONS[state.language] || TRANSLATIONS.it;
  if (key in dict) return dict[key];
  const extra = EXTRA[state.language] || EXTRA.it;
  return key in extra ? extra[key] : key;
}

// Calls one of TRANSLATIONS' (or EXTRA's) function-valued entries
// (summaryRunning, deleteConfirmBody, ...) directly, the same fallback order
// t() uses for plain string keys.
function tFn(key, ...args) {
  const dict = TRANSLATIONS[state.language] || TRANSLATIONS.it;
  if (key in dict) return dict[key](...args);
  const extra = EXTRA[state.language] || EXTRA.it;
  return extra[key](...args);
}

// Maps the internal mode key ("full"/"master"/"slave" - unchanged in
// settings.db, the CLI --mode flag and orchestration/tests) to its
// user-facing display name (Diretta/Solo Upload/Solo installazione, or the
// English equivalent).
const MODE_TITLE_KEYS = { full: "modeFullTitle", master: "modeMasterTitle", slave: "modeSlaveTitle" };
function modeDisplayName(modeKey) {
  return t(MODE_TITLE_KEYS[modeKey] || modeKey);
}

const MAPPING_PAGE_SIZE = 8;

function readmeUrl(anchor) {
  const base =
    state.language === "en"
      ? "https://github.com/Seroper-real/lmu-setup-manager/blob/main/readme.md"
      : "https://github.com/Seroper-real/lmu-setup-manager/blob/main/readme.it.md";
  return anchor ? `${base}#${anchor}` : base;
}

function api() {
  return window.pywebview && window.pywebview.api;
}

function debounce(fn, delay) {
  let handle;
  return (...args) => {
    clearTimeout(handle);
    handle = setTimeout(() => fn(...args), delay);
  };
}

function formatDate(ms) {
  if (!ms) return "-";
  return new Date(ms).toLocaleDateString();
}

function getVal(id) {
  const el = document.getElementById(id);
  return el ? el.value : "";
}

function getChecked(id) {
  const el = document.getElementById(id);
  return el ? el.checked : false;
}

function showToast(message, kind) {
  const root = document.getElementById("toast-root");
  const div = document.createElement("div");
  div.className = `toast ${kind === "success" ? "toast-success" : kind === "error" ? "toast-error" : ""}`;
  div.textContent = message;
  root.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}

function infoTip(tip) {
  return `<span class="info-tip">${ICONS.info}<span class="info-tip-text">${escapeHtml(tip)}</span></span>`;
}

// ----- bootstrap / init -------------------------------------------------------

function waitForPywebview() {
  return new Promise((resolve) => {
    if (window.pywebview) return resolve();
    window.addEventListener("pywebviewready", resolve, { once: true });
  });
}

function buildSettingsForm(bootstrap) {
  const env = bootstrap.env || {};
  const cfg = bootstrap.config || {};
  const logging = cfg.logging || {};
  const network = cfg.network || {};
  const paths = cfg.paths || {};
  const remoteTracks = cfg.remote_mappings || {};
  const dropbox = cfg.dropbox || {};

  return {
    lmuPath: bootstrap.lmuPath || "",
    lmuPathValid: bootstrap.lmuPathExists !== false,
    env: {
      ACCESS_TOKEN_LIST: env.ACCESS_TOKEN_LIST || "",
      ACCESS_TOKEN_DOWNLOAD: env.ACCESS_TOKEN_DOWNLOAD || "",
      USER_ID: env.USER_ID || "",
      DROPBOX_APP_KEY: env.DROPBOX_APP_KEY || "",
      DROPBOX_APP_SECRET: env.DROPBOX_APP_SECRET || "",
      DROPBOX_REFRESH_TOKEN: env.DROPBOX_REFRESH_TOKEN || "",
    },
    logLevel: logging.level || "DEBUG",
    minDelay: network.min_delay !== undefined ? network.min_delay : 0.5,
    maxDelay: network.max_delay !== undefined ? network.max_delay : 1.5,
    timeout: network.timeout !== undefined ? network.timeout : 30,
    pageSize: network.page_size !== undefined ? network.page_size : 64,
    cleanDownload: !!(paths.download && paths.download.clean_download_after_copy),
    overwrite: !!(paths.setups && paths.setups.overwrite),
    deletePreviousVersion: !!(paths.setups && paths.setups.delete_previous_version),
    remoteTracksEnabled: !!remoteTracks.enabled,
    remoteTracksUrl: remoteTracks.url || "",
    remoteTracksTimeout: remoteTracks.timeout !== undefined ? remoteTracks.timeout : 5,
    dropboxFolder: dropbox.folder || "",
    dropboxTimeout: dropbox.timeout !== undefined ? dropbox.timeout : 30,
    dropboxUploadWorkers: dropbox.upload_workers !== undefined ? dropbox.upload_workers : 4,
  };
}

async function init() {
  await waitForPywebview();
  try {
    const bootstrap = await api().get_bootstrap();
    state.bootstrap = bootstrap;
    state.language = bootstrap.language || "it";
    state.selectedMode = bootstrap.mode || "full";
    state.showWarning = !bootstrap.hymoWarningDismissed;
    state.settingsForm = buildSettingsForm(bootstrap);
    state.settingsSavedSnapshot = JSON.stringify(state.settingsForm);
    await refreshInstalled();
  } catch (e) {
    console.error("Failed to load bootstrap", e);
  }
  render();
}

async function refreshInstalled() {
  state.installedData = await api().list_installed_setups(state.installedSearch);
}

// Unlike refreshInstalled (server-side search), the mapping tab's row set is
// small and fetched whole every visit; renderMappingView() does search/sort/
// pagination client-side over it.
async function refreshMappings() {
  state.manualMappings = await api().list_manual_mappings();
}

// ----- progress push channel (Python -> JS) -----------------------------------

window.onProgress = function onProgress(event) {
  // START and INSTALL fire back-to-back for the same setup with the identical
  // title/meta (see main.py/slave_manager.py's shared `label`), and
  // renderActivityItem gives neither an icon - pushed as two separate items
  // they read as the same setup logged twice. Update the still-open "start"
  // row in place instead of appending a second one; only search backward
  // for one still in the "start" kind, so an already-installed row with a
  // reused title (e.g. a second run) isn't mistaken for this one.
  if (event.kind === "install") {
    const pending = [...state.activity].reverse().find(
      (e) => e.kind === "start" && e.title === event.title && e.meta === event.meta,
    );
    if (pending) {
      pending.kind = "install";
    } else {
      state.activity.push(event);
    }
  } else {
    state.activity.push(event);
  }
  let runEnded = false;
  if (event.kind === "start") {
    state.running = true;
    state.runStatus = "running";
  } else if (event.kind === "finish") {
    state.running = false;
    state.runStatus = "completed";
    runEnded = true;
  } else if (event.kind === "stopped") {
    state.running = false;
    state.runStatus = "stopped";
    runEnded = true;
  } else if (event.kind === "error") {
    state.running = false;
    state.runStatus = "error";
    runEnded = true;
    if (event.authError) {
      state.authErrorCode = event.errorCode || "generic";
      state.authErrorStatus = event.errorStatus || null;
      renderModals();
    }
  }
  if (state.view === "download") renderDownloadView();
  renderSidebar();

  // The DB only reflects new installs once the run has stopped producing them;
  // refresh the Setup installati data/count so the user does not have to poke
  // the search box to see what a run just installed.
  if (runEnded) {
    refreshInstalled().then(() => {
      renderSidebar();
      if (state.view === "setups") renderSetupsView();
    });
  }

  // Setups skipped this run because their car/track didn't match -
  // mapping.json + manual_mapping fallback both missed. Offer the
  // end-of-run correction dialog (see openUnmatchedModal below).
  if (
    (event.kind === "finish" || event.kind === "stopped") && event.unmatched &&
    (event.unmatched.tracks.length || event.unmatched.cars.length)
  ) {
    openUnmatchedModal(event.unmatched);
  }
};

// Live progress push channel for the Danger Zone's "clean Dropbox setups"
// action (see confirmDangerAction/api.py's clean_dropbox_setups) - fires
// repeatedly while that one blocking API call is still in flight.
window.onDangerProgress = function onDangerProgress(deletedCount, phase) {
  state.dangerDeletedCount = deletedCount;
  state.dangerPhase = phase || "deleting";
  if (state.dangerTarget && state.dangerBusy) renderModals();
};

// Result push channel for the TrackTitan automatic token-fetch flow (the
// second pywebview window opened by tracktitan_fetch_tokens_start()) - see
// its click handler and the waiting modal in renderModals().
window.onTrackTitanTokens = async function onTrackTitanTokens(result) {
  state.tracktitanFetch = null;
  renderModals();
  if (result.ok) {
    Object.entries(result.tokens).forEach(([key, value]) => {
      const input = document.getElementById(`f-${key}`);
      if (input) input.value = value;
    });
    await persistSettings();
    showToast(t("tracktitanFetchSuccessToast"), "success");
  } else if (result.reason === "timeout") {
    showToast(t("tracktitanFetchTimeoutToast"), "error");
  }
  // "cancelled" (user closed the popup or hit Annulla) stays silent - it's an
  // ordinary user action, not a failure worth a toast.
};

// Python's events.closing handler (webview's FormClosing) cancels the native
// close and calls this when Settings has unsaved edits, since it can't cross
// the JS/native boundary synchronously to ask - Api.confirm_close() re-fires
// the actual close once the user resolves the prompt below.
window.onRequestCloseConfirmation = function onRequestCloseConfirmation() {
  state.unsavedChangesPrompt = { reason: "close" };
  renderModals();
};

// ----- top-level render ---------------------------------------------------

function render() {
  renderSidebar();
  renderSetupsView();
  renderDownloadView();
  renderUploadView();
  renderMappingView();
  renderSettingsView();
  applyActiveView();
  renderModals();
}

function applyActiveView() {
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  const active = document.getElementById(`view-${state.view}`);
  if (active) active.classList.add("active");
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === state.view);
  });
}

// applyActiveView() only toggles which view is visible - it never re-renders
// one, so navigating to Setups showed whatever was last rendered there (e.g.
// still empty from init(), or missing setups installed by a run watched from
// the Download tab). Refresh from the DB on every visit so newly installed
// setups show up immediately.
function goToView(target) {
  state.view = target;
  applyActiveView();
  if (state.view === "setups") {
    refreshInstalled().then(() => {
      renderSetupsView();
      renderSidebar();
    });
  } else if (state.view === "upload") {
    ensureUploadOptions().then(() => renderUploadView());
  } else if (state.view === "mapping") {
    refreshMappings().then(() => renderMappingView());
  }
}

// ----- sidebar --------------------------------------------------------------

// Shared by #nav and #nav-bottom (see renderSidebar) - the sidebar's second
// group (mapping/settings, pushed to the bottom) needs the identical
// markup/click-binding logic as the primary group, just rendered into a
// different container.
function renderNavItemsHtml(items) {
  return items
    .map(
      (i) => `
        <button class="nav-item" data-view="${i.view}">
          <span class="nav-icon">${i.icon}</span><span>${escapeHtml(i.label)}</span>
        </button>
      `
    )
    .join("");
}

function bindNavItemClicks(containerEl) {
  containerEl.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.view;
      // Leaving Settings with unsaved edits: hold off navigating until the
      // user resolves the prompt (see resolveUnsavedChangesPrompt()).
      if (state.view === "settings" && target !== "settings" && isSettingsDirty()) {
        state.unsavedChangesPrompt = { reason: "nav", target };
        renderModals();
        return;
      }
      goToView(target);
    });
  });
}

function renderSidebar() {
  document.getElementById("logo-sub").textContent = "Setup Manager";

  const nav = document.getElementById("nav");
  nav.innerHTML = renderNavItemsHtml([
    { view: "setups", icon: ICONS.navSetups, label: t("navSetups") },
    { view: "download", icon: ICONS.navDownload, label: t("navDownload") },
    { view: "upload", icon: ICONS.navUpload, label: t("navUpload") },
  ]);
  bindNavItemClicks(nav);

  const navBottom = document.getElementById("nav-bottom");
  navBottom.innerHTML =
    `<div class="hr"></div>` +
    renderNavItemsHtml([
      { view: "mapping", icon: ICONS.navMapping, label: t("navMapping") },
      { view: "settings", icon: ICONS.navSettings, label: t("navSettings") },
    ]);
  bindNavItemClicks(navBottom);

  // state.selectedMode is the single source of truth for the current mode: it's
  // seeded from bootstrap.mode at init() and kept in sync on every mode-card
  // click via set_mode() (see renderDownloadView). Reading state.bootstrap.mode
  // here instead would freeze the badge at whatever mode the app started in,
  // since bootstrap is only fetched once - the bug this fixes.
  document.getElementById("mode-badge").innerHTML = `
    <span>${escapeHtml(t("sidebarMode"))}</span>
    <span class="tag tag-accent">${escapeHtml(modeDisplayName(state.selectedMode))}</span>
    ${state.bootstrap && state.bootstrap.sandboxActive ? `<span class="tag tag-warning">SANDBOX</span>` : ""}
  `;

  document.getElementById("installed-count").innerHTML = `
    <span>${escapeHtml(t("sidebarInstalled"))}</span>
    <strong>${state.installedData.grandTotal}</strong>
  `;

  document.getElementById("app-version").innerHTML = `
    <span>${escapeHtml(t("sidebarVersion"))}</span>
    <strong>${escapeHtml(state.bootstrap && state.bootstrap.appVersion ? state.bootstrap.appVersion : "")}</strong>
  `;

  applyActiveView();
}

// ----- Setup installati -------------------------------------------------------

function renderSetupsView() {
  const el = document.getElementById("view-setups");

  const search = state.installedSearch.trim();
  const emptyText = search
    ? `${t("noResultsPrefix")}${escapeHtml(search)}${t("noResultsSuffix")}`
    : escapeHtml(t("emptySetupsList"));

  const groupsHtml = state.installedData.groups.length
    ? state.installedData.groups.map(renderTrackGroup).join("")
    : `<div class="empty-state">${emptyText}</div>`;

  el.innerHTML = `
    <div class="view-header">
      <div>
        <h2>${escapeHtml(t("setupsTitle"))}</h2>
        <p>${escapeHtml(t("setupsDesc"))}</p>
      </div>
    </div>
    <div class="toolbar">
      <div class="search-field">
        ${ICONS.search}
        <input type="text" class="input" id="setups-search" placeholder="${escapeHtml(t("searchPlaceholder"))}" value="${escapeHtml(state.installedSearch)}">
      </div>
      <span class="tag tag-outline results-count">${state.installedData.totalCount} ${escapeHtml(t("resultsWord"))}</span>
      <button type="button" class="btn btn-ghost text-danger toolbar-push-end" id="setups-delete-all-btn" ${state.installedData.grandTotal ? "" : "disabled"}>${ICONS.trash}${escapeHtml(t("deleteAllInstalledButton"))}</button>
    </div>
    <div class="setups-list">${groupsHtml}</div>
  `;

  document.getElementById("setups-search").addEventListener(
    "input",
    debounce((e) => {
      state.installedSearch = e.target.value;
      refreshInstalled().then(() => {
        renderSetupsView();
        renderSidebar();
        focusSetupsSearchInput();
      });
    }, 250)
  );

  document.getElementById("setups-delete-all-btn").addEventListener("click", () => {
    state.deleteTarget = { allInstalled: true };
    renderModals();
  });

  el.querySelectorAll("[data-toggle-track]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.toggleTrack;
      if (state.expandedTracks.has(key)) state.expandedTracks.delete(key);
      else state.expandedTracks.add(key);
      renderSetupsView();
    });
  });

  el.querySelectorAll("[data-toggle-car-group]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.toggleCarGroup;
      if (state.expandedCarGroups.has(key)) state.expandedCarGroups.delete(key);
      else state.expandedCarGroups.add(key);
      renderSetupsView();
    });
  });

  el.querySelectorAll("[data-toggle-car]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.toggleCar;
      if (state.expandedCars.has(key)) state.expandedCars.delete(key);
      else state.expandedCars.add(key);
      renderSetupsView();
    });
  });

  el.querySelectorAll("[data-delete-setup]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.deleteTarget = {
        setupIds: [btn.dataset.deleteSetup],
        car: btn.dataset.car,
        track: btn.dataset.track,
        all: false,
      };
      renderModals();
    });
  });

  el.querySelectorAll("[data-delete-type-ids]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.deleteTarget = {
        setupIds: JSON.parse(btn.dataset.deleteTypeIds),
        car: btn.dataset.car,
        track: btn.dataset.track,
        groupType: btn.dataset.deleteType,
        all: true,
      };
      renderModals();
    });
  });

  el.querySelectorAll("[data-delete-track]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.deleteTarget = {
        setupIds: JSON.parse(btn.dataset.deleteTrackIds),
        track: btn.dataset.deleteTrack,
        all: true,
      };
      renderModals();
    });
  });
}

// Cards render collapsed by default and expand on click; a non-empty search
// forces every card open so results are never hidden behind a collapsed
// header. Grouping already keeps each render to one DOM subtree per physical
// track (see list_installed_setups' matched_track_id grouping), which is what
// keeps this manageable without real pagination/virtualization - worth
// revisiting only if a single account's track *count* itself grows very large,
// and even then windowing would have to keep each track's cars together.
function renderTrackGroup(group) {
  const isSearching = !!state.installedSearch.trim();
  const expanded = isSearching || state.expandedTracks.has(group.track);

  const allSetups = group.cars.flatMap((c) => c.types.flatMap((ty) => ty.setups));
  const rows = group.cars.map((c) => renderCarGroup(group, c)).join("");
  const setupIds = allSetups.map((s) => s.setupId);

  return `
    <div class="card elev-sm setup-track-card">
      <div class="track-group-header">
        <button type="button" class="track-toggle" data-toggle-track="${escapeHtml(group.track)}">
          <span class="chevron ${expanded ? "expanded" : ""}">${ICONS.chevron}</span>
          <h4>${escapeHtml(group.track)}</h4>
        </button>
        <div class="track-group-actions">
          <span class="tooltip">
            <button type="button" class="btn btn-ghost text-danger" data-delete-track="${escapeHtml(group.track)}" data-delete-track-ids="${escapeHtml(JSON.stringify(setupIds))}">${ICONS.trash}</button>
            <span class="tooltip-text">${escapeHtml(t("deleteAllButton"))}</span>
          </span>
          <span class="tag tag-outline group-count">${allSetups.length}</span>
        </div>
      </div>
      ${expanded ? `<div class="setup-rows">${rows}</div>` : ""}
    </div>
  `;
}

// One row per unique car in the track, regardless of how many installed setups
// it has (a car can carry both a HYMO and a GO setup at once - see
// renderSetupEntry, which tags each row with its type). Independent accordion
// from the track card's own expand/collapse; expanding reveals every setup
// this car actually has installed, HYMO and/or GO alike.
function renderCarGroup(group, carGroup) {
  const isSearching = !!state.installedSearch.trim();
  const key = `${group.track}::${carGroup.car}`;
  const expanded = isSearching || state.expandedCarGroups.has(key);
  const totalCount = carGroup.types.reduce((n, ty) => n + ty.setups.length, 0);

  const rowsHtml = carGroup.types
    .flatMap((ty) => ty.setups.map((s, i) => renderSetupEntry(s, group, ty, i === 0)))
    .join("");

  const classLogo = carGroup.carClass
    ? `<img class="car-class-logo" src="assets/class-logos/${encodeURIComponent(carGroup.carClass)}.png" alt="${escapeHtml(carGroup.carClass)}">`
    : "";

  return `
    <div class="setup-car">
      <div class="setup-car-header">
        <button type="button" class="setup-car-toggle" data-toggle-car-group="${escapeHtml(key)}">
          <span class="chevron ${expanded ? "expanded" : ""}">${ICONS.chevron}</span>
          ${classLogo}
          <span class="car">${escapeHtml(carGroup.car)}</span>
        </button>
        <span class="tag tag-outline group-count">${totalCount}</span>
      </div>
      ${expanded ? `<div class="setup-types">${rowsHtml}</div>` : ""}
    </div>
  `;
}

// One installed setup's own accordion, independent of the car group's
// expand/collapse: clicking its header reveals the individual setup file names
// installed for it (s.fileNames), instead of just the aggregate file count.
// The HYMO/GO badge lives on this same row (rather than a separate group
// header) since most cars only ever have one setup per type, which made a
// dedicated header row mostly empty space; the redundant per-type count that
// used to sit next to it is gone for the same reason. When a type has more
// than one setup (e.g. multiple HYMO variants), the first entry also carries
// a "delete all of this type" button, distinct from its own per-entry delete.
function renderSetupEntry(s, group, ty, isFirst) {
  const entryExpanded = state.expandedCars.has(s.setupId);
  const badge = `<span class="tag tag-outline">${escapeHtml(ty.type)}</span>`;

  const files = (s.fileNames || [])
    .map((name) => `<div class="setup-file">${escapeHtml(name)}</div>`)
    .join("");

  const bulkDeleteButton = isFirst && ty.setups.length > 1
    ? `<span class="tooltip">
         <button type="button" class="btn btn-ghost text-danger" data-delete-type-ids="${escapeHtml(JSON.stringify(ty.setups.map((x) => x.setupId)))}" data-delete-type="${escapeHtml(ty.type)}" data-car="${escapeHtml(s.car)}" data-track="${escapeHtml(group.track)}">${ICONS.trash}</button>
         <span class="tooltip-text">${escapeHtml(tFn("deleteGroupButtonTooltip", ty.type))}</span>
       </span>`
    : "";

  return `
    <div class="setup-entry">
      <div class="setup-entry-header">
        <button type="button" class="setup-entry-toggle" data-toggle-car="${escapeHtml(s.setupId)}">
          <span class="chevron ${entryExpanded ? "expanded" : ""}">${ICONS.chevron}</span>
          ${badge}
          <span class="meta">${formatDate(s.installDate)}</span>
        </button>
        <span class="tag tag-outline">${s.fileCount} ${escapeHtml(t("filesUnit"))}</span>
        ${s.installationFolder ? `<span class="meta meta-icon">${ICONS.folder}${escapeHtml(s.installationFolder)}</span>` : ""}
        ${s.hotlapLink
          ? `<a class="btn btn-ghost" href="#" data-open-link="${escapeHtml(s.hotlapLink)}" title="${escapeHtml(t("hotlapTitle"))}">${ICONS.hotlap}${escapeHtml(t("hotlapLabel"))}</a>`
          : ""}
        ${bulkDeleteButton}
        <span class="tooltip">
          <button type="button" class="btn btn-ghost text-danger" data-delete-setup="${escapeHtml(s.setupId)}" data-car="${escapeHtml(s.car)}" data-track="${escapeHtml(group.track)}">${ICONS.trash}</button>
          <span class="tooltip-text">${escapeHtml(t("deleteButton"))}</span>
        </span>
      </div>
      ${entryExpanded ? `<div class="setup-files">${files}</div>` : ""}
    </div>
  `;
}

// ----- Download ---------------------------------------------------------------

// Desc-key family for each view's compact, read-only mode-summary card
// (renderModeSummaryCard below), keyed by mode. Download and Upload each
// phrase the same three modes' effects differently (Download: what a Start
// download run does; Upload: what confirming a manual upload does), so they
// don't share Settings' own general-purpose picker copy either (see
// renderModePickerCards's modeGeneralFullDesc/MasterDesc/SlaveDesc).
const DOWNLOAD_MODE_DESC_KEYS = { full: "fullDesc", master: "masterDesc", slave: "slaveDesc" };

// Compact, read-only stand-in for the full mode picker (now in Settings, see
// renderModePickerCards) - shows the active mode + a shortcut back to Settings
// to change it. Shared by Download and Upload, which only differ in which
// desc-key family they pass.
function renderModeSummaryCard(descKeys) {
  return `
    <div class="card elev-sm mode-summary">
      <div class="mode-summary-info">
        <span class="tag tag-accent">${escapeHtml(modeDisplayName(state.selectedMode))}</span>
        <p>${escapeHtml(t(descKeys[state.selectedMode]))}</p>
      </div>
      <button type="button" class="btn btn-secondary" data-goto-settings-mode>${escapeHtml(t("changeModeButton"))}</button>
    </div>
  `;
}

// No unsaved-changes guard here (unlike the sidebar nav, see renderSidebar):
// that guard only matters when *leaving* Settings, not when navigating to it.
function bindModeSummaryCard(el) {
  const btn = el.querySelector("[data-goto-settings-mode]");
  if (btn) btn.addEventListener("click", () => goToView("settings"));
}

function renderDownloadView() {
  const el = document.getElementById("view-download");

  const statusLabelKey =
    { idle: "statusIdle", running: "statusRunning", completed: "statusCompleted", stopped: "statusStopped", error: "statusError" }[state.runStatus] ||
    "statusIdle";

  const installedThisRun = state.activity.filter((e) => e.kind === "install").length;
  const installedSummary =
    state.runStatus === "running"
      ? tFn("summaryRunning", installedThisRun)
      : state.activity.length
      ? tFn("summaryCompleted", installedThisRun)
      : t("summaryIdle");

  const activityHtml = state.activity.length
    ? state.activity.slice(-200).map(renderActivityItem).join("")
    : `<div class="empty-state">${escapeHtml(t("emptyLog"))}</div>`;

  el.innerHTML = `
    <div class="view-header">
      <div>
        <h2>${escapeHtml(t("downloadTitle"))}</h2>
        <p>${escapeHtml(t("downloadDescPre"))}<strong>${escapeHtml(modeDisplayName(state.selectedMode))}</strong>${escapeHtml(t("downloadDescPost"))}</p>
      </div>
    </div>
    ${renderModeSummaryCard(DOWNLOAD_MODE_DESC_KEYS)}
    <div class="card elev-md status-card">
      <div class="status-left">
        <span class="status-dot ${state.running ? "running" : state.runStatus}"></span>
        <div class="status-text">
          <strong>${escapeHtml(t(statusLabelKey))}</strong>
          <span>${escapeHtml(installedSummary)}</span>
        </div>
      </div>
      <button type="button" class="btn ${state.running ? "btn-secondary" : "btn-primary"}" id="start-stop-btn">
        ${state.running ? ICONS.stop : ICONS.play}${escapeHtml(state.running ? t("stopButton") : t("startButton"))}
      </button>
    </div>
    <div>
      <h6 class="text-muted">${escapeHtml(t("activityHeading"))}</h6>
      <div class="card activity-log" id="activity-log">${activityHtml}</div>
    </div>
  `;

  bindModeSummaryCard(el);
  document.getElementById("start-stop-btn").addEventListener("click", onStartStopClick);

  const log = document.getElementById("activity-log");
  if (log) log.scrollTop = log.scrollHeight;
}

function renderActivityItem(item) {
  const icons = {
    stopped: ICONS.activityStopped,
    error: ICONS.activityError,
    install: ICONS.activityInstalled,
  };
  const icon = icons[item.kind];
  return `
    <div class="activity-item kind-${item.kind}">
      ${icon ? `<span class="activity-icon">${icon}</span>` : ""}
      <div>
        <div class="title">${escapeHtml(item.title)}</div>
        ${item.meta ? `<div class="meta">${escapeHtml(item.meta)}</div>` : ""}
      </div>
    </div>
  `;
}

// Validates and kicks off a run in state.selectedMode. Shared by the Download
// tab's start button (onStartStopClick below) and the unmatched-setups
// dialog's "Salva e Risegui" (see renderModals' data-unmatched-save-rerun
// binding), which restarts the same run after saving new mappings.
async function startRun() {
  const errors = await api().validate_start(state.selectedMode);
  if (errors && errors.length) {
    state.validationErrors = errors;
    renderModals();
    return;
  }

  state.activity = [];
  state.runStatus = "running";
  state.running = true;
  renderDownloadView();

  const result = await api().start_download(state.selectedMode);
  if (!result || !result.started) {
    state.running = false;
    state.runStatus = "idle";
    renderDownloadView();
  }
}

async function onStartStopClick() {
  if (state.running) {
    await api().stop_download();
    return;
  }
  await startRun();
}

// ----- Carica Setup / manual upload ---------------------------------------

const UPLOAD_MODE_DESC_KEYS = { full: "uploadFullDesc", master: "uploadMasterDesc", slave: "uploadSlaveDesc" };

// Lazy-fetched once: both lists are static per mapping.json load, so a first
// visit to the Upload tab is the only time either needs an IPC round trip.
async function ensureUploadOptions() {
  if (!state.trackFolderOptions.length) {
    state.trackFolderOptions = await api().get_track_folder_options();
  }
  if (!state.uploadCarOptions.length) {
    state.uploadCarOptions = await api().get_car_options();
  }
}

async function onPickSetupZip() {
  const picked = await api().pick_setup_zip_file();
  if (!picked) return;
  const fileName = picked.split(/[\\/]/).pop();
  state.manualUpload = { filePath: picked, fileName, type: "GO", track: null, car: null };
  state.uploadOpenDropdown = null;
  state.uploadDropdownSearch = {};
  state.uploadDropdownHighlight = {};
  await ensureUploadOptions();
  renderUploadView();
  applyGuessedIdentity(fileName);
}

// Best-effort car/track pre-fill from the file name (e.g.
// "GO-FERRARI-499P-SEBRING.zip" -> Ferrari 499P / Sebring), run after the
// dropdowns are already rendered with empty selections so the user sees
// them fill in rather than waiting on this round trip before anything shows.
// Guarded on fileName still matching in case a second file was picked/dropped
// before this resolved.
async function applyGuessedIdentity(fileName) {
  const guess = await api().guess_manual_upload_identity(fileName);
  if (!guess || !state.manualUpload || state.manualUpload.fileName !== fileName) return;
  if (guess.car) state.manualUpload.car = guess.car;
  if (guess.track) state.manualUpload.track = guess.track;
  if (guess.car || guess.track) renderUploadView();
}

// Base64-encodes an ArrayBuffer in chunks (avoids blowing the call stack on
// String.fromCharCode.apply for larger files).
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}

// Handles a file dropped on the upload-dropzone. WebView2 never exposes a
// dropped File's real filesystem path, so the bytes are read client-side and
// handed to save_dropped_setup_file(), which writes them to disk and hands
// back a path usable exactly like pick_setup_zip_file()'s return value.
async function onDropSetupZip(file) {
  if (!file || !/\.zip$/i.test(file.name)) {
    showToast(t("manualUploadInvalidFileToast"), "error");
    return;
  }
  const base64 = arrayBufferToBase64(await file.arrayBuffer());
  const savedPath = await api().save_dropped_setup_file(file.name, base64);
  if (!savedPath) return;
  state.manualUpload = { filePath: savedPath, fileName: file.name, type: "GO", track: null, car: null };
  state.uploadOpenDropdown = null;
  state.uploadDropdownSearch = {};
  state.uploadDropdownHighlight = {};
  await ensureUploadOptions();
  renderUploadView();
  applyGuessedIdentity(file.name);
}

// The WebView2 shell's default behavior for a file dropped anywhere on the
// page is to navigate to it (opening a Windows Explorer window for a .zip) -
// block that globally; the upload-dropzone's own handler (see
// renderUploadView) is the only place a drop is actually handled. Setting
// dropEffect to "none" also makes the OS show a forbidden/no-drop cursor
// everywhere except the dropzone, whose own dragover handler below sets it
// back to "copy" and stops the event from bubbling up to this listener.
window.addEventListener("dragover", (e) => {
  e.preventDefault();
  if (e.dataTransfer) e.dataTransfer.dropEffect = "none";
});
window.addEventListener("drop", (e) => e.preventDefault());

// Generic searchable dropdown shared by the Track and Car fields below -
// options are `{value, label, carClass?}`; carClass (when withLogos is set)
// renders the same class-logo <img> renderCarGroup() uses for installed setups.
// clearable adds a fixed "clear selection" row above the (searchable, so
// possibly filtered-out) option list, letting a value already picked be
// reset back to the placeholder without hunting for it again.
function renderSearchableSelect({ id, options, selected, placeholder, withLogos, clearable }) {
  const isOpen = state.uploadOpenDropdown === id;
  const query = (state.uploadDropdownSearch[id] || "").trim().toLowerCase();
  const filtered = query ? options.filter((o) => o.label.toLowerCase().includes(query)) : options;
  const selectedOption = options.find((o) => o.value === selected);
  // Arrow-key highlight, clamped to the current (possibly filtered) list so a
  // stale index from before a search never points past the end of it.
  const highlighted = Math.min(Math.max(state.uploadDropdownHighlight[id] || 0, 0), Math.max(filtered.length - 1, 0));
  const logo = (opt) =>
    withLogos && opt && opt.carClass
      ? `<img class="car-class-logo" src="assets/class-logos/${encodeURIComponent(opt.carClass)}.png" alt="">`
      : "";

  return `
    <div class="select-dropdown" data-select-id="${id}">
      <button type="button" class="input select-trigger" data-select-toggle="${id}">
        <span class="select-trigger-value">
          ${selectedOption ? `${logo(selectedOption)}${escapeHtml(selectedOption.label)}` : `<span class="text-muted">${escapeHtml(placeholder)}</span>`}
        </span>
        <span class="select-trigger-chevron">${ICONS.chevron}</span>
      </button>
      ${isOpen ? `
        <div class="select-panel">
          <input type="text" class="input" data-select-search="${id}" placeholder="${escapeHtml(t("manualUploadSearchPlaceholder"))}" value="${escapeHtml(state.uploadDropdownSearch[id] || "")}">
          ${clearable && selected ? `
            <button type="button" class="select-option select-option-clear" data-select-clear="${id}">
              ${escapeHtml(t("selectClearOption"))}
            </button>
          ` : ""}
          <div class="select-options">
            ${filtered.length
              ? filtered
                  .map(
                    (o, i) => `
                      <button type="button" class="select-option ${o.value === selected ? "selected" : ""} ${i === highlighted ? "highlighted" : ""}" data-select-option="${id}" data-value="${escapeHtml(o.value)}">
                        ${logo(o)}${escapeHtml(o.label)}
                      </button>
                    `
                  )
                  .join("")
              : `<div class="select-empty">${escapeHtml(t("manualUploadNoResults"))}</div>`}
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

// Refocuses a dropdown's search input after a renderUploadView() call has
// just replaced it with a fresh DOM node (search filters/highlights instantly
// on every keystroke/arrow-press, so losing focus each time would make
// keyboard use unusable), restoring the caret to the end of its text.
function focusDropdownSearchInput(id) {
  const fresh = document.querySelector(`[data-select-search="${id}"]`);
  if (fresh) {
    fresh.focus();
    const pos = fresh.value.length;
    fresh.setSelectionRange(pos, pos);
  }
}

// Same rebuilt-input-loses-focus problem as focusDropdownSearchInput above,
// for the "setup installati" page's own search box (renderSetupsView's
// debounced input handler rebuilds #setups-search via innerHTML on every
// keystroke pause, which drops focus unless it's explicitly restored here).
function focusSetupsSearchInput() {
  const fresh = document.getElementById("setups-search");
  if (fresh) {
    fresh.focus();
    const pos = fresh.value.length;
    fresh.setSelectionRange(pos, pos);
  }
}

// Returns focus to a dropdown's own trigger button once Enter/Escape closes
// its panel, so keyboard users don't lose their place when the search input
// they were just typing in disappears from the DOM.
function focusDropdownTrigger(id) {
  const trigger = document.querySelector(`[data-select-toggle="${id}"]`);
  if (trigger) trigger.focus();
}

// Binds one renderSearchableSelect() instance. `onSelect` mutates the
// caller's own state (state.manualUpload.track/.car, or one row of
// state.unmatchedTarget.items) directly rather than returning a value,
// since the caller also owns when to re-render - which is why `rerender`
// is passed in explicitly rather than hardcoded: the Upload tab re-renders
// itself via renderUploadView(), the end-of-run unmatched-setups dialog via
// renderModals(), same component either way.
function bindSearchableSelect(el, id, onSelect, rerender) {
  const root = el.querySelector(`.select-dropdown[data-select-id="${id}"]`);
  if (!root) return;

  root.querySelector("[data-select-toggle]").addEventListener("click", () => {
    const opening = state.uploadOpenDropdown !== id;
    state.uploadOpenDropdown = opening ? id : null;
    state.uploadDropdownSearch[id] = "";
    state.uploadDropdownHighlight[id] = 0;
    rerender();
    // rerender() just built the search input fresh - focus it so users can
    // start typing to filter immediately, without an extra click.
    if (opening) focusDropdownSearchInput(id);
  });

  const searchInput = root.querySelector("[data-select-search]");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      state.uploadDropdownSearch[id] = e.target.value;
      state.uploadDropdownHighlight[id] = 0;
      rerender();
      focusDropdownSearchInput(id);
    });

    // Arrow keys move the highlight through the currently rendered (i.e.
    // already filtered) option list; Enter picks whichever one is
    // highlighted, same as a native <select>. Reading the option list back
    // from the freshly-rendered DOM (rather than re-deriving the filter here)
    // keeps this in sync with renderSearchableSelect's own filtering by
    // construction.
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const count = root.querySelectorAll("[data-select-option]").length;
        if (!count) return;
        const current = state.uploadDropdownHighlight[id] || 0;
        const next = e.key === "ArrowDown" ? Math.min(current + 1, count - 1) : Math.max(current - 1, 0);
        state.uploadDropdownHighlight[id] = next;
        rerender();
        focusDropdownSearchInput(id);
      } else if (e.key === "Enter") {
        e.preventDefault();
        const optionEls = root.querySelectorAll("[data-select-option]");
        const target = optionEls[state.uploadDropdownHighlight[id] || 0];
        if (!target) return;
        onSelect(target.dataset.value);
        state.uploadOpenDropdown = null;
        state.uploadDropdownSearch[id] = "";
        rerender();
        focusDropdownTrigger(id);
      } else if (e.key === "Escape") {
        e.preventDefault();
        state.uploadOpenDropdown = null;
        rerender();
        focusDropdownTrigger(id);
      }
    });
  }

  root.querySelectorAll("[data-select-option]").forEach((btn) => {
    btn.addEventListener("click", () => {
      onSelect(btn.dataset.value);
      state.uploadOpenDropdown = null;
      state.uploadDropdownSearch[id] = "";
      rerender();
    });
  });

  const clearBtn = root.querySelector("[data-select-clear]");
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      onSelect(null);
      state.uploadOpenDropdown = null;
      state.uploadDropdownSearch[id] = "";
      rerender();
    });
  }
}

// Closes whichever select-dropdown is open on an outside click - same pattern
// as closeContextMenu()'s own outside-mousedown listener further down. Picks
// the rerender matching whichever surface (Upload tab vs. the unmatched-setups
// dialog) actually owns the currently-open dropdown id.
document.addEventListener("mousedown", (e) => {
  if (state.uploadOpenDropdown && !e.target.closest(".select-dropdown")) {
    state.uploadOpenDropdown = null;
    if (state.unmatchedTarget) renderModals();
    else renderUploadView();
  }
});

function renderManualUploadForm(upload) {
  const trackOptions = state.trackFolderOptions.map((folder) => ({ value: folder, label: folder }));
  const carOptions = state.uploadCarOptions.map((c) => ({ value: c.name, label: c.name, carClass: c.carClass }));
  const canConfirm = !!(upload.track && upload.car);

  return `
    <div class="card elev-sm">
      <div class="field">
        <label>${escapeHtml(t("manualUploadFileLabel"))}</label>
        <div class="input-group">
          <input class="input" value="${escapeHtml(upload.fileName)}" readonly>
          <button type="button" class="btn btn-secondary" id="manual-upload-change-file-btn">${escapeHtml(t("browseButton"))}</button>
        </div>
      </div>
      <div class="field">
        <label>${escapeHtml(t("manualUploadTypeLabel"))}</label>
        <select class="input" id="manual-upload-type-select">
          <option value="GO" ${upload.type === "GO" ? "selected" : ""}>GO Setups</option>
          <option value="HYMO" ${upload.type === "HYMO" ? "selected" : ""}>HYMO</option>
        </select>
      </div>
      <div class="field">
        <label>${escapeHtml(t("manualUploadTrackLabel"))}</label>
        ${renderSearchableSelect({ id: "track", options: trackOptions, selected: upload.track, placeholder: t("manualUploadTrackPlaceholder") })}
      </div>
      <div class="field">
        <label>${escapeHtml(t("manualUploadCarLabel"))}</label>
        ${renderSearchableSelect({ id: "car", options: carOptions, selected: upload.car, placeholder: t("manualUploadCarPlaceholder"), withLogos: true })}
      </div>
      <div class="dialog-actions" style="justify-content:flex-start; margin-top: var(--space-2);">
        <button type="button" class="btn btn-ghost" id="manual-upload-cancel-btn">${escapeHtml(t("manualUploadCancel"))}</button>
        <button type="button" class="btn btn-primary" id="manual-upload-confirm-btn" ${canConfirm ? "" : "disabled"}>${escapeHtml(t("manualUploadConfirm"))}</button>
      </div>
    </div>
  `;
}

function bindManualUploadForm(el, upload) {
  document.getElementById("manual-upload-change-file-btn").addEventListener("click", onPickSetupZip);

  document.getElementById("manual-upload-cancel-btn").addEventListener("click", () => {
    state.manualUpload = null;
    state.uploadOpenDropdown = null;
    renderUploadView();
  });

  const typeSelect = document.getElementById("manual-upload-type-select");
  if (typeSelect) {
    typeSelect.addEventListener("change", () => { upload.type = typeSelect.value; });
  }

  bindSearchableSelect(el, "track", (value) => { upload.track = value; }, renderUploadView);
  bindSearchableSelect(el, "car", (value) => { upload.car = value; }, renderUploadView);

  const confirmBtn = document.getElementById("manual-upload-confirm-btn");
  if (confirmBtn) confirmBtn.addEventListener("click", onConfirmManualUpload);
}

async function onConfirmManualUpload() {
  const upload = state.manualUpload;
  if (!upload || !upload.track || !upload.car) return;

  const errors = await api().validate_start(state.selectedMode);
  if (errors && errors.length) {
    state.validationErrors = errors;
    renderModals();
    return;
  }

  const confirmBtn = document.getElementById("manual-upload-confirm-btn");
  if (confirmBtn) confirmBtn.disabled = true;

  const result = await api().upload_manual_setup(upload.filePath, upload.type, upload.track, upload.car);
  if (!result || !result.ok) {
    if (result && result.authError) {
      state.authErrorCode = result.errorCode || "generic";
      state.authErrorStatus = result.errorStatus || null;
      renderModals();
    } else {
      showToast((result && result.error) || t("manualUploadGenericErrorToast"), "error");
    }
    if (confirmBtn) confirmBtn.disabled = false;
    return;
  }

  state.manualUpload = null;
  state.uploadOpenDropdown = null;
  renderUploadView();
  showToast(t("manualUploadSuccessToast"), "success");

  // Master never installs locally, so the Setup installati list has nothing
  // new to show - only refresh it for the modes that actually write to the DB.
  if (state.selectedMode !== "master") {
    await refreshInstalled();
    renderSetupsView();
    renderSidebar();
  }
}

function renderUploadView() {
  const el = document.getElementById("view-upload");
  const upload = state.manualUpload;

  const dropzoneHtml = `
    <div class="card elev-sm upload-dropzone" id="upload-dropzone-trigger" role="button" tabindex="0">
      <span class="upload-dropzone-icon">${ICONS.uploadCloud}</span>
      <h3>${escapeHtml(t("uploadDropzoneTitle"))}</h3>
      <p>${escapeHtml(t("uploadDropzoneDesc"))}</p>
    </div>
  `;

  el.innerHTML = `
    <div class="view-header">
      <div>
        <h2>${escapeHtml(t("uploadPageTitle"))}</h2>
        <p>${escapeHtml(t("uploadPageDesc"))}</p>
      </div>
    </div>
    ${renderModeSummaryCard(UPLOAD_MODE_DESC_KEYS)}
    ${upload ? renderManualUploadForm(upload) : dropzoneHtml}
  `;

  bindModeSummaryCard(el);

  if (upload) {
    bindManualUploadForm(el, upload);
  } else {
    const dropzone = document.getElementById("upload-dropzone-trigger");
    dropzone.addEventListener("click", onPickSetupZip);
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      dropzone.classList.add("drag-over");
    });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("drag-over");
      onDropSetupZip(e.dataTransfer.files[0]);
    });
  }
}

// ----- Settings -----------------------------------------------------------

// renderSettingsView() does a full innerHTML replace of the view (same as
// every other render*() in this file), which throws away whatever the user
// typed but hasn't saved yet. Any handler that re-renders the settings view
// without an intervening save (toggle-token-secrets, toggle-dropbox-secrets,
// advanced-toggle, language)
// must call this first so state.settingsForm - the data the next render
// reads from - reflects the live DOM instead of the stale bootstrap/last-save
// snapshot. input.value always holds the real string regardless of the
// masked/unmasked type="password" toggle, so this is safe to call in either
// visibility state.
function captureSettingsForm() {
  const f = state.settingsForm;
  if (!f) return;
  const lmuInput = document.getElementById("lmu-path-input");
  if (lmuInput) f.lmuPath = lmuInput.value;
  if (document.getElementById("f-ACCESS_TOKEN_LIST")) {
    f.env.ACCESS_TOKEN_LIST = getVal("f-ACCESS_TOKEN_LIST");
    f.env.ACCESS_TOKEN_DOWNLOAD = getVal("f-ACCESS_TOKEN_DOWNLOAD");
    f.env.USER_ID = getVal("f-USER_ID");
    f.env.DROPBOX_APP_KEY = getVal("f-DROPBOX_APP_KEY");
    f.env.DROPBOX_APP_SECRET = getVal("f-DROPBOX_APP_SECRET");
    f.env.DROPBOX_REFRESH_TOKEN = getVal("f-DROPBOX_REFRESH_TOKEN");
    f.dropboxFolder = getVal("f-dropboxFolder");
  }
  if (state.advancedOpen && document.getElementById("f-logLevel")) {
    f.logLevel = getVal("f-logLevel");
    // Numeric fields are read back as Number, not the raw input string -
    // buildSettingsForm() populates these from config as numbers, so leaving
    // them as strings here made isSettingsDirty() report a false positive
    // (type mismatch, not a real edit) any time the advanced section was
    // simply opened and closed again.
    f.pageSize = Number(getVal("f-pageSize"));
    f.timeout = Number(getVal("f-timeout"));
    f.minDelay = Number(getVal("f-minDelay"));
    f.maxDelay = Number(getVal("f-maxDelay"));
    f.cleanDownload = getChecked("f-cleanDownload");
    f.overwrite = getChecked("f-overwrite");
    f.deletePreviousVersion = getChecked("f-deletePreviousVersion");
    f.remoteTracksEnabled = getChecked("f-remoteTracksEnabled");
    f.remoteTracksUrl = getVal("f-remoteTracksUrl");
    f.remoteTracksTimeout = Number(getVal("f-remoteTracksTimeout"));
    f.dropboxTimeout = Number(getVal("f-dropboxTimeout"));
    f.dropboxUploadWorkers = Number(getVal("f-dropboxUploadWorkers"));
  }
}

// Whether the live Settings form differs from the last persisted snapshot.
// Always captures first so edits sitting in currently-visible fields (the
// advanced section included, when open) are accounted for before comparing.
function isSettingsDirty() {
  if (!state.settingsForm || !state.settingsSavedSnapshot) return false;
  captureSettingsForm();
  return JSON.stringify(state.settingsForm) !== state.settingsSavedSnapshot;
}

// Mirrors the dirty flag to the Python side, which cannot otherwise tell -
// when the user hits the native window close button, Api.handle_window_closing
// checks this mirrored flag directly rather than reaching back into JS
// synchronously mid-close.
function pushSettingsDirty() {
  const dirty = isSettingsDirty();
  api().mark_settings_dirty(dirty);
  return dirty;
}

// Credential keys are stored/looked-up by their real env var name (e.g.
// "ACCESS_TOKEN_LIST"), but that name is only readable as a UI label - purely
// cosmetic, never touches the id/value used to save or capture the field.
function displayKey(key) {
  return key.replace(/_/g, " ");
}

// A masked field's real value is always readable via input.value (masking is
// purely a rendering thing), so the copy button sources from there directly
// instead of depending on however this webview's Ctrl+C/selection handling
// treats a type="password" field. Used for every text/password field in
// Settings, masked or not, for a standardized copy affordance.
function copyField(id, label, value, type, titleAction) {
  const labelHtml = titleAction
    ? `<div class="field-label-row"><label>${escapeHtml(label)}</label>${titleAction}</div>`
    : `<label>${escapeHtml(label)}</label>`;
  return `
    <div class="field">
      ${labelHtml}
      <div class="input-group">
        <input class="input" type="${type}" id="${id}" value="${escapeHtml(value)}">
        <button type="button" class="btn btn-secondary" data-copy="${id}" title="${escapeHtml(t("copyButton"))}">${ICONS.copy}</button>
      </div>
    </div>
  `;
}

// The full, clickable 3-mode picker - lives here (rather than Download/Upload,
// which now only show renderModeSummaryCard's compact read-only stand-in)
// since the mode is an app-wide setting, not something specific to either of
// those workflows.
function renderModePickerCards() {
  const modes = [
    { key: "full", title: t("modeFullTitle"), desc: t("modeGeneralFullDesc") },
    { key: "master", title: t("modeMasterTitle"), desc: t("modeGeneralMasterDesc") },
    { key: "slave", title: t("modeSlaveTitle"), desc: t("modeGeneralSlaveDesc") },
  ];
  return modes
    .map(
      (m) => `
        <button type="button" class="mode-card ${state.selectedMode === m.key ? "selected" : ""}" data-mode="${m.key}">
          <div class="card-header">
            <h3>${m.title}</h3>
            ${state.selectedMode === m.key ? `<span class="tag tag-accent">${escapeHtml(t("activeTag"))}</span>` : ""}
          </div>
          <p>${escapeHtml(m.desc)}</p>
        </button>
      `
    )
    .join("");
}

// ----- Mappature manuali -----------------------------------------------------

// Client-side search/sort/paginate over state.manualMappings - shared between
// renderMappingView (row rendering) and the mapping-delete-all confirm dialog
// in renderModals, whose body count uses the unfiltered total regardless of
// an active search (matching the mock's own behavior).
function getMappingViewModel() {
  const search = state.mappingSearch.trim().toLowerCase();
  const filtered = state.manualMappings
    .filter(
      (row) => !search || row.name.toLowerCase().includes(search) || row.matcher.toLowerCase().includes(search)
    )
    .sort((a, b) => {
      if (a.type !== b.type) return a.type === "track" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
  const pageCount = Math.max(1, Math.ceil(filtered.length / MAPPING_PAGE_SIZE));
  const page = Math.min(state.mappingPage, pageCount - 1);
  const pageRows = filtered.slice(page * MAPPING_PAGE_SIZE, page * MAPPING_PAGE_SIZE + MAPPING_PAGE_SIZE);
  return { filtered, pageCount, page, pageRows };
}

// Same rebuilt-input-loses-focus problem as focusSetupsSearchInput, for the
// mapping tab's own search box.
function focusMappingSearchInput() {
  const fresh = document.getElementById("mapping-search");
  if (fresh) {
    fresh.focus();
    const pos = fresh.value.length;
    fresh.setSelectionRange(pos, pos);
  }
}

function renderMappingView() {
  const el = document.getElementById("view-mapping");
  if (!el) return;

  const { filtered, pageCount, page, pageRows } = getMappingViewModel();
  state.mappingPage = page;

  const rowsHtml = pageRows
    .map(
      (row) => `
        <tr>
          <td><span class="tag ${row.type === "track" ? "tag-accent" : "tag-accent-2"}">${escapeHtml(row.type === "track" ? t("mappingTypeTrack") : t("mappingTypeCar"))}</span></td>
          <td>${escapeHtml(row.name)}</td>
          <td class="mapping-matcher">${escapeHtml(row.matcher)}</td>
          <td class="mapping-actions-col">
            <span class="tooltip">
              <button type="button" class="btn btn-ghost text-danger" data-delete-mapping="${escapeHtml(row.id)}" data-delete-mapping-name="${escapeHtml(row.name)}">${ICONS.trash}</button>
              <span class="tooltip-text">${escapeHtml(t("deleteButton"))}</span>
            </span>
          </td>
        </tr>
      `
    )
    .join("");

  const tableHtml = filtered.length
    ? `
      <div class="card elev-sm" style="padding:0; overflow:hidden;">
        <table class="table">
          <thead>
            <tr>
              <th>${escapeHtml(t("mappingColType"))}</th>
              <th>${escapeHtml(t("mappingColName"))}</th>
              <th>${escapeHtml(t("mappingColMatcher"))}</th>
              <th class="mapping-actions-col">${escapeHtml(t("mappingColActions"))}</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      </div>
      <div class="pagination">
        <span class="pagination-label">${escapeHtml(tFn("mappingPageLabel", page + 1, pageCount))}</span>
        <button type="button" class="btn btn-ghost" id="mapping-prev-page" ${page === 0 ? "disabled" : ""}>${escapeHtml(t("mappingPrevPage"))}</button>
        <button type="button" class="btn btn-ghost" id="mapping-next-page" ${page >= pageCount - 1 ? "disabled" : ""}>${escapeHtml(t("mappingNextPage"))}</button>
      </div>
    `
    : `<div class="empty-state">${escapeHtml(t("mappingEmptyText"))}</div>`;

  el.innerHTML = `
    <div class="view-header">
      <div>
        <h2>${escapeHtml(t("mappingTitle"))}</h2>
        <p>${escapeHtml(t("mappingDesc"))}</p>
      </div>
    </div>
    <div class="toolbar">
      <div class="search-field">
        ${ICONS.search}
        <input type="text" class="input" id="mapping-search" placeholder="${escapeHtml(t("mappingSearchPlaceholder"))}" value="${escapeHtml(state.mappingSearch)}">
      </div>
      <span class="tag tag-outline results-count">${filtered.length} ${escapeHtml(t("mappingResultsWord"))}</span>
      <button type="button" class="btn btn-ghost text-danger toolbar-push-end" id="mapping-delete-all-btn" ${state.manualMappings.length ? "" : "disabled"}>${ICONS.trash}${escapeHtml(t("mappingDeleteAllButton"))}</button>
    </div>
    ${tableHtml}
  `;

  document.getElementById("mapping-search").addEventListener(
    "input",
    debounce((e) => {
      state.mappingSearch = e.target.value;
      state.mappingPage = 0;
      renderMappingView();
      focusMappingSearchInput();
    }, 250)
  );

  document.getElementById("mapping-delete-all-btn").addEventListener("click", () => {
    state.mappingDeleteTarget = { kind: "all" };
    renderModals();
  });

  el.querySelectorAll("[data-delete-mapping]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.mappingDeleteTarget = { kind: "row", id: btn.dataset.deleteMapping, name: btn.dataset.deleteMappingName };
      renderModals();
    });
  });

  const prevBtn = document.getElementById("mapping-prev-page");
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      state.mappingPage = Math.max(0, state.mappingPage - 1);
      renderMappingView();
    });
  }

  const nextBtn = document.getElementById("mapping-next-page");
  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      state.mappingPage = Math.min(getMappingViewModel().pageCount - 1, state.mappingPage + 1);
      renderMappingView();
    });
  }
}

function renderSettingsView() {
  const el = document.getElementById("view-settings");
  if (!state.settingsForm) {
    el.innerHTML = "";
    return;
  }
  const f = state.settingsForm;
  const tokenSecretType = state.showTokenSecrets ? "text" : "password";
  const dropboxSecretType = state.showDropboxSecrets ? "text" : "password";
  const tokenUrl = readmeUrl(state.language === "en" ? "tracktitan-tokens" : "token-tracktitan");
  const dropboxUrl = readmeUrl(state.language === "en" ? "dropbox-credentials" : "credenziali-dropbox");

  el.innerHTML = `
    <div class="view-header">
      <div>
        <h2>${escapeHtml(t("settingsTitle"))}</h2>
        <p>${escapeHtml(t("settingsDesc"))}</p>
      </div>
    </div>

    <div>
      <h6 class="text-muted">${escapeHtml(t("modeSectionHeading"))}</h6>
      <div class="card elev-sm mode-cards">${renderModePickerCards()}</div>
    </div>

    <div class="hr"></div>
    <div>
      <h6 class="text-muted">${escapeHtml(t("langHeading"))}</h6>
      <div class="card elev-sm">
        <div class="field" style="margin-bottom:0;">
          <label>${escapeHtml(t("langFieldLabel"))}</label>
          <div class="seg" id="lang-seg">
            <button type="button" class="seg-opt ${state.language === "it" ? "active" : ""}" data-lang="it">Italiano</button>
            <button type="button" class="seg-opt ${state.language === "en" ? "active" : ""}" data-lang="en">English</button>
          </div>
        </div>
      </div>
    </div>

    <div>
      <h6 class="text-muted">${escapeHtml(t("lmuHeading"))}</h6>
      <div class="card elev-sm">
        <div class="field" style="margin-bottom:4px;">
          <label>${escapeHtml(t("lmuFieldLabel"))}</label>
          <div class="input-group">
            <input class="input" id="lmu-path-input" value="${escapeHtml(f.lmuPath)}">
            <button type="button" class="btn btn-secondary" data-copy="lmu-path-input" title="${escapeHtml(t("copyButton"))}">${ICONS.copy}</button>
            <button type="button" class="btn btn-secondary" id="browse-btn">${ICONS.folderBrowse}${escapeHtml(t("browseButton"))}</button>
          </div>
          <div class="field-warning" id="lmu-path-warning" style="${f.lmuPathValid ? "display:none;" : ""}">${ICONS.fieldWarning}${escapeHtml(t("lmuPathInvalidWarning"))}</div>
        </div>
        <p class="help-text">${escapeHtml(t("lmuHelp"))}</p>
      </div>
    </div>

    <div class="hr"></div>
    <div>
      <div class="section-heading-row">
        <button type="button" class="btn btn-ghost" id="toggle-token-secrets" title="${escapeHtml(state.showTokenSecrets ? t("hideValues") : t("showValues"))}">${state.showTokenSecrets ? ICONS.eyeOpen : ICONS.eyeClosed}</button>
        <h6 class="text-muted">${escapeHtml(t("tokenHeading"))}</h6>
      </div>
      <p class="text-muted" style="font-size:13px;">${escapeHtml(t("tokenHelp"))}</p>
      ${copyField(
        "f-ACCESS_TOKEN_LIST",
        displayKey("ACCESS_TOKEN_LIST"),
        f.env.ACCESS_TOKEN_LIST,
        tokenSecretType,
        `<a href="#" class="field-hint-link" id="tracktitan-fetch-start-btn">${ICONS.externalLink}${escapeHtml(t("tracktitanFetchButton"))}</a>`
      )}
      ${copyField("f-ACCESS_TOKEN_DOWNLOAD", displayKey("ACCESS_TOKEN_DOWNLOAD"), f.env.ACCESS_TOKEN_DOWNLOAD, tokenSecretType)}
      ${copyField("f-USER_ID", displayKey("USER_ID"), f.env.USER_ID, "text")}
      <a href="#" class="readme-link" data-open-link="${tokenUrl}">${ICONS.externalLink}${escapeHtml(t("tokenLinkText"))}</a>
    </div>

    <div class="hr"></div>
    <div>
      <div class="section-heading-row">
        <button type="button" class="btn btn-ghost" id="toggle-dropbox-secrets" title="${escapeHtml(state.showDropboxSecrets ? t("hideValues") : t("showValues"))}">${state.showDropboxSecrets ? ICONS.eyeOpen : ICONS.eyeClosed}</button>
        <h6 class="text-muted">${escapeHtml(t("dropboxHeading"))}</h6>
      </div>
      <p class="text-muted" style="font-size:13px;">${escapeHtml(t("dropboxHelp"))}</p>
      ${copyField("f-DROPBOX_APP_KEY", displayKey("DROPBOX_APP_KEY"), f.env.DROPBOX_APP_KEY, "text")}
      ${copyField("f-DROPBOX_APP_SECRET", displayKey("DROPBOX_APP_SECRET"), f.env.DROPBOX_APP_SECRET, dropboxSecretType)}
      ${copyField(
        "f-DROPBOX_REFRESH_TOKEN",
        displayKey("DROPBOX_REFRESH_TOKEN"),
        f.env.DROPBOX_REFRESH_TOKEN,
        dropboxSecretType,
        `<a href="#" class="field-hint-link" id="dropbox-oauth-start-btn">${ICONS.externalLink}${escapeHtml(t("dropboxOauthButton"))}</a>`
      )}
      ${copyField("f-dropboxFolder", t("dropboxFolderLabel"), f.dropboxFolder, "text")}
      <a href="#" class="readme-link" data-open-link="${dropboxUrl}">${ICONS.externalLink}${escapeHtml(t("dropboxLinkText"))}</a>
    </div>

    <div class="hr"></div>
    <div>
      <div class="settings-row-header" id="advanced-toggle">
        <h6 class="text-muted" style="margin:0;">${escapeHtml(t("advancedHeading"))}</h6>
        <button type="button" class="btn btn-ghost">${escapeHtml(state.advancedOpen ? t("advancedHide") : t("advancedShow"))}</button>
      </div>
      ${state.advancedOpen ? `<div class="card elev-sm">${renderAdvancedFields(f)}</div>` : ""}
    </div>

    <div class="hr"></div>
    <div>
      <h6 class="text-danger">${escapeHtml(t("dangerZoneHeading"))}</h6>
      <div class="card elev-sm card-danger">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:var(--space-4); padding:var(--space-2) 0;">
          <div style="display:flex; flex-direction:column; gap:2px;">
            <span style="font-size:14px; color:var(--color-text);">${escapeHtml(t("dangerCleanSetupsTitle"))}</span>
            <span style="font-size:12.5px; color:var(--color-neutral-500);">${escapeHtml(t("dangerCleanSetupsDesc"))}</span>
          </div>
          <button type="button" class="btn btn-danger" id="danger-clean-dropbox-btn" style="white-space:nowrap; flex:none;">${escapeHtml(t("dangerCleanSetupsButton"))}</button>
        </div>
        <div class="hr" style="margin:0;"></div>
        <div style="display:flex; align-items:center; justify-content:space-between; gap:var(--space-4); padding:var(--space-2) 0;">
          <div style="display:flex; flex-direction:column; gap:2px;">
            <span style="font-size:14px; color:var(--color-text);">${escapeHtml(t("dangerCleanAllTitle"))}</span>
            <span style="font-size:12.5px; color:var(--color-neutral-500);">${escapeHtml(t("dangerCleanAllDesc"))}</span>
          </div>
          <button type="button" class="btn btn-danger" id="danger-restore-factory-btn" style="white-space:nowrap; flex:none;">${escapeHtml(t("dangerCleanAllButton"))}</button>
        </div>
      </div>
    </div>
  `;

  el.querySelectorAll(".mode-cards .mode-card").forEach((btn) => {
    btn.addEventListener("click", async () => {
      // state.selectedMode is not part of the captured settingsForm snapshot
      // (see its declaration at the top of this file) - it's persisted and
      // applied immediately via set_mode(), not queued for the next Save. Still
      // capture first, since the innerHTML replace below (renderSettingsView())
      // would otherwise discard whatever the user typed into other fields but
      // hasn't saved yet.
      captureSettingsForm();
      state.selectedMode = btn.dataset.mode;
      await api().set_mode(state.selectedMode);
      renderSettingsView();
      renderDownloadView();
      renderSidebar();
    });
  });

  document.getElementById("toggle-token-secrets").addEventListener("click", () => {
    captureSettingsForm();
    state.showTokenSecrets = !state.showTokenSecrets;
    renderSettingsView();
  });

  document.getElementById("toggle-dropbox-secrets").addEventListener("click", () => {
    captureSettingsForm();
    state.showDropboxSecrets = !state.showDropboxSecrets;
    renderSettingsView();
  });

  el.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const input = document.getElementById(btn.dataset.copy);
      if (!input) return;
      try {
        await navigator.clipboard.writeText(input.value);
      } catch (e) {
        // Fallback for hosts where the async Clipboard API is unavailable:
        // temporarily unmask + select the field and use the legacy
        // execCommand copy path, which piggybacks on this click's user
        // gesture the same way Ctrl+C normally would.
        const previousType = input.type;
        input.type = "text";
        input.select();
        document.execCommand("copy");
        input.type = previousType;
      }
      showToast(t("copiedToast"), "success");
    });
  });

  el.querySelectorAll("#lang-seg [data-lang]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      captureSettingsForm();
      state.language = btn.dataset.lang;
      await api().set_language(state.language);
      render();
    });
  });

  document.getElementById("dropbox-oauth-start-btn").addEventListener("click", async (e) => {
    e.preventDefault();
    const appKey = getVal("f-DROPBOX_APP_KEY").trim();
    const appSecret = getVal("f-DROPBOX_APP_SECRET").trim();
    if (!appKey || !appSecret) {
      showToast(t("dropboxOauthNeedKeysToast"), "error");
      return;
    }
    state.dropboxOAuth = { step: "choice", appKey, appSecret };
    renderModals();
  });

  document.getElementById("tracktitan-fetch-start-btn").addEventListener("click", async (e) => {
    e.preventDefault();
    const result = await api().tracktitan_fetch_tokens_start();
    if (!result || !result.started) return;
    state.tracktitanFetch = {};
    renderModals();
  });

  document.getElementById("lmu-path-input").addEventListener(
    "input",
    debounce(async (e) => {
      const valid = await api().check_lmu_path(e.target.value.trim());
      f.lmuPathValid = valid;
      const warning = document.getElementById("lmu-path-warning");
      if (warning) warning.style.display = valid ? "none" : "flex";
    }, 400)
  );

  document.getElementById("browse-btn").addEventListener("click", async () => {
    const current = document.getElementById("lmu-path-input").value;
    const picked = await api().browse_lmu_folder(current);
    if (picked) {
      document.getElementById("lmu-path-input").value = picked;
      f.lmuPathValid = true;
      const warning = document.getElementById("lmu-path-warning");
      if (warning) warning.style.display = "none";
      pushSettingsDirty();
    }
  });

  document.getElementById("advanced-toggle").addEventListener("click", () => {
    captureSettingsForm();
    state.advancedOpen = !state.advancedOpen;
    renderSettingsView();
  });

  document.getElementById("danger-clean-dropbox-btn").addEventListener("click", () => {
    startDangerCountdown("dropbox");
    renderModals();
  });

  document.getElementById("danger-restore-factory-btn").addEventListener("click", () => {
    startDangerCountdown("factory");
    renderModals();
  });
}

// ----- danger zone (settings) ------------------------------------------------

function startDangerCountdown(kind) {
  clearInterval(_dangerTimer);
  state.dangerTarget = { kind };
  state.dangerCountdown = 5;
  state.dangerBusy = false;
  _dangerTimer = setInterval(() => {
    state.dangerCountdown -= 1;
    if (state.dangerCountdown <= 0) {
      clearInterval(_dangerTimer);
      state.dangerCountdown = 0;
    }
    renderModals();
  }, 1000);
}

function cancelDangerConfirm() {
  clearInterval(_dangerTimer);
  state.dangerTarget = null;
  state.dangerCountdown = 0;
  state.dangerBusy = false;
  renderModals();
}

async function confirmDangerAction() {
  if (!state.dangerTarget || state.dangerCountdown > 0 || state.dangerBusy) return;
  clearInterval(_dangerTimer);
  const kind = state.dangerTarget.kind;
  state.dangerBusy = true;
  renderModals();

  if (kind === "dropbox") {
    state.dangerDeletedCount = 0;
    state.dangerPhase = "deleting";
    const result = await api().clean_dropbox_setups();
    state.dangerTarget = null;
    state.dangerBusy = false;
    renderModals();
    if (!result || !result.ok) {
      if (result && result.authError) {
        state.authErrorCode = result.errorCode || "generic";
        state.authErrorStatus = result.errorStatus || null;
        renderModals();
      } else {
        showToast((result && result.error) || t("dangerCleanGenericErrorToast"), "error");
      }
      return;
    }
    showToast(t("dangerCleanedSetupsToast"), "success");
  } else {
    await api().restore_factory_settings();
    state.dangerTarget = null;
    state.dangerBusy = false;

    state.bootstrap = await api().get_bootstrap();
    state.language = state.bootstrap.language || "it";
    state.selectedMode = state.bootstrap.mode || "full";
    state.showWarning = !state.bootstrap.hymoWarningDismissed;
    state.settingsForm = buildSettingsForm(state.bootstrap);
    state.settingsSavedSnapshot = JSON.stringify(state.settingsForm);
    await refreshInstalled();

    renderSettingsView();
    renderSetupsView();
    renderSidebar();
    renderModals();
    showToast(t("dangerCleanedAllToast"), "success");
  }
}

function renderAdvancedFields(f) {
  const textField = (id, labelKey, tipKey, value, type) => `
    <div class="field">
      <label>${escapeHtml(t(labelKey))} ${infoTip(t(tipKey))}</label>
      <div class="input-group">
        <input class="input" type="${type || "text"}" id="${id}" value="${escapeHtml(value)}">
        <button type="button" class="btn btn-secondary" data-copy="${id}" title="${escapeHtml(t("copyButton"))}">${ICONS.copy}</button>
      </div>
    </div>
  `;
  const checkField = (id, labelKey, tipKey, checked) => `
    <label style="display:flex; align-items:center; gap:8px; font-size:14px; cursor:pointer; margin-bottom: var(--space-4);">
      <input type="checkbox" id="${id}" ${checked ? "checked" : ""}> ${escapeHtml(t(labelKey))} ${infoTip(t(tipKey))}
    </label>
  `;

  return `
    <span class="text-muted" style="font-size:12px; letter-spacing:0.06em; text-transform:uppercase;">${escapeHtml(t("logSection"))}</span>
    <div class="field">
      <label>${escapeHtml(t("logLevelLabel"))} ${infoTip(t("logLevelTip"))}</label>
      <select class="input" id="f-logLevel">
        ${["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].map(lvl =>
          `<option value="${lvl}" ${lvl === f.logLevel ? "selected" : ""}>${lvl}</option>`
        ).join("")}
      </select>
    </div>
    <div class="hr"></div>
    <span class="text-muted" style="font-size:12px; letter-spacing:0.06em; text-transform:uppercase;">${escapeHtml(t("networkSection"))}</span>
    <div class="field-row">
      ${textField("f-pageSize", "pageSizeLabel", "pageSizeTip", f.pageSize, "number")}
      ${textField("f-timeout", "timeoutLabel", "networkTimeoutTip", f.timeout, "number")}
      ${textField("f-minDelay", "minDelayLabel", "minDelayTip", f.minDelay, "number")}
      ${textField("f-maxDelay", "maxDelayLabel", "maxDelayTip", f.maxDelay, "number")}
    </div>
    <div class="hr"></div>
    <span class="text-muted" style="font-size:12px; letter-spacing:0.06em; text-transform:uppercase;">${escapeHtml(t("downloadSetupSection"))}</span>
    ${checkField("f-cleanDownload", "cleanDownloadLabel", "cleanDownloadTip", f.cleanDownload)}
    ${checkField("f-overwrite", "overwriteLabel", "overwriteTip", f.overwrite)}
    ${checkField("f-deletePreviousVersion", "deletePrevLabel", "deletePrevTip", f.deletePreviousVersion)}
    <div class="hr"></div>
    <span class="text-muted" style="font-size:12px; letter-spacing:0.06em; text-transform:uppercase;">${escapeHtml(t("remoteTracksSection"))}</span>
    ${checkField("f-remoteTracksEnabled", "remoteEnabledLabel", "remoteEnabledTip", f.remoteTracksEnabled)}
    ${textField("f-remoteTracksUrl", "remoteUrlLabel", "remoteUrlTip", f.remoteTracksUrl)}
    ${textField("f-remoteTracksTimeout", "timeoutLabel", "remoteTimeoutTip", f.remoteTracksTimeout, "number")}
    <div class="hr"></div>
    <span class="text-muted" style="font-size:12px; letter-spacing:0.06em; text-transform:uppercase;">${escapeHtml(t("dropboxAdvSection"))}</span>
    <div class="field-row">
      ${textField("f-dropboxTimeout", "timeoutLabel", "dropboxTimeoutTip", f.dropboxTimeout, "number")}
      ${textField("f-dropboxUploadWorkers", "uploadWorkersLabel", "uploadWorkersTip", f.dropboxUploadWorkers, "number")}
    </div>
  `;
}

// The single settings-persistence path, now that there is no manual Save
// button: called after an automatic token retrieval completes, and from the
// unsaved-changes prompt's "Save" action (nav-away or app-close). Reads from
// state.settingsForm (post-capture) rather than gating each section's DOM
// lookup on state.advancedOpen, since a value edited earlier in the session
// and then collapsed must still be included.
async function persistSettings() {
  captureSettingsForm();
  const f = state.settingsForm;

  const envValues = { ...f.env };
  const configPatch = {
    paths: {
      setups: {
        lmu_base_path: f.lmuPath,
        overwrite: !!f.overwrite,
        delete_previous_version: !!f.deletePreviousVersion,
      },
      download: {
        clean_download_after_copy: !!f.cleanDownload,
      },
    },
    dropbox: {
      folder: f.dropboxFolder,
      timeout: parseInt(f.dropboxTimeout, 10),
      upload_workers: parseInt(f.dropboxUploadWorkers, 10),
    },
    logging: { level: f.logLevel },
    network: {
      min_delay: parseFloat(f.minDelay),
      max_delay: parseFloat(f.maxDelay),
      timeout: parseInt(f.timeout, 10),
      page_size: parseInt(f.pageSize, 10),
    },
    remote_mappings: {
      enabled: !!f.remoteTracksEnabled,
      url: f.remoteTracksUrl,
      timeout: parseInt(f.remoteTracksTimeout, 10),
    },
  };

  await api().save_settings(envValues, configPatch);

  // Settings hot-reload instead of relaunching the process: re-fetch bootstrap
  // so the form (and the mode badge/sandbox tag, in case anything else
  // changed underneath) reflects exactly what was just persisted, and reset
  // the dirty snapshot to that new baseline.
  state.bootstrap = await api().get_bootstrap();
  state.settingsForm = buildSettingsForm(state.bootstrap);
  state.settingsSavedSnapshot = JSON.stringify(state.settingsForm);
  renderSettingsView();
  renderSidebar();
  await api().mark_settings_dirty(false);
}

// The unsaved-changes prompt's "Discard" action: reverts the form to whatever
// is actually persisted in settings.db. Re-fetches bootstrap rather than
// reusing the in-memory state.bootstrap, since that cached copy can predate
// changes made outside this form (e.g. set_mode()/set_language() update the
// DB directly without refreshing it) - discarding must restore the real DB
// state, not a stale in-memory guess at it.
async function discardSettingsChanges() {
  state.bootstrap = await api().get_bootstrap();
  state.settingsForm = buildSettingsForm(state.bootstrap);
  state.settingsSavedSnapshot = JSON.stringify(state.settingsForm);
  renderSettingsView();
  api().mark_settings_dirty(false);
}

// Advances the Dropbox OAuth dialog from the read-only/read-write choice step
// to the code-paste step: requests an authorize URL scoped to the chosen
// token type, opens it in the system browser, then swaps the modal.
async function startDropboxOauthFlow(tokenType) {
  const { appKey, appSecret } = state.dropboxOAuth;
  const result = await api().dropbox_oauth_get_url(appKey, appSecret, tokenType);
  if (!result || result.error) {
    showToast((result && result.error) || t("dropboxOauthGenericError"), "error");
    state.dropboxOAuth = null;
    renderModals();
    return;
  }
  await api().open_external_link(result.url);
  state.dropboxOAuth = { step: "code", appKey, appSecret };
  renderModals();
}

// ----- modals (warning / validation) --------------------------------

// Our real check_credentials() returns a flat list of missing/invalid field
// names rather than the mock's single validateCredentials() error type, since
// a run can be short on both TrackTitan and Dropbox credentials at once. Pick
// the matching real sentence(s) for whichever family of fields shows up.
function validationBody(errors, mode) {
  const modeLabel = modeDisplayName(mode);
  const hasTrackTitan = errors.some((e) => e.includes("ACCESS_TOKEN") || e.includes("USER_ID"));
  const hasDropbox = errors.some((e) => e.includes("DROPBOX"));
  const hasLmuPath = errors.some((e) => e.includes("LMU_PATH"));
  const sentences = [];
  if (hasTrackTitan) sentences.push(tFn("validationMissingTrackTitan", modeLabel));
  if (hasDropbox) sentences.push(tFn("validationMissingDropbox", modeLabel));
  if (hasLmuPath) sentences.push(tFn("validationInvalidLmuPath", modeLabel));
  // No raw `errors` bullet list here: every string check_credentials()/
  // validate_start() can produce is English-only (env var names) and is
  // already fully covered, in the user's language, by the sentences above.
  return sentences.map((s) => `<p>${escapeHtml(s)}</p>`).join("");
}

// Localizes an AuthError surfaced mid-run (see window.onProgress) from its
// `code`/`status` instead of the English `title` used for the activity log,
// so this dialog shows in the user's active app language.
function authErrorBody(code, status) {
  if (code === "tracktitan") return tFn("authErrorTrackTitanBody", status);
  if (code === "dropbox_scope") return t("authErrorDropboxScopeBody");
  if (code === "dropbox") return t("authErrorDropboxBody");
  return t("authErrorGenericBody");
}

// Populates and opens the end-of-run "unmatched setups" dialog from the
// run's {tracks, cars} payload (each already a unique list - see
// domain.unmatched.UnmatchedTracker.serialize on the Python side, which
// dedupes by value so hundreds of setups sharing one unmatched track/car
// only ever need a single correction). Reuses ensureUploadOptions() (see the
// Upload tab above) for the same two dropdown option lists (track folders,
// cars) the per-step correction picks from - already cached after a first
// Upload tab visit, so this is a no-op IPC-wise in the common case.
async function openUnmatchedModal(unmatched) {
  await ensureUploadOptions();
  state.unmatchedTarget = {
    // Shown one track/car value at a time via the dialog's stepper (see
    // renderModals) - saving the current one advances this to the next.
    currentIndex: 0,
    items: [
      ...(unmatched.tracks || []).map((name) => ({ kind: "track", name, selected: null })),
      ...(unmatched.cars || []).map((name) => ({ kind: "car", name, selected: null })),
    ],
  };
  renderModals();
}

// Persists every populated, valid selection across all unmatched items in one
// batch - an item left blank simply contributes nothing. Shared by the
// dialog's "Salva e Chiudi"/"Salva e Risegui" buttons (see the
// data-unmatched-save-close/-rerun bindings).
async function saveAllUnmatchedMappings() {
  const calls = [];
  for (const item of state.unmatchedTarget.items) {
    if (!item.selected) continue;
    calls.push(item.kind === "track" ? api().map_track(item.name, item.selected) : api().map_car(item.name, item.selected));
  }
  await Promise.all(calls);
}

function renderModals() {
  const root = document.getElementById("modal-root");
  let html = "";

  if (state.showWarning) {
    html += `
      <div class="dialog-backdrop" data-modal="warning">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.warning}${escapeHtml(t("warningTitle"))}</div>
          <div class="dialog-body">${escapeHtml(t("warningBody"))}</div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-primary" id="warning-dismiss">${escapeHtml(t("warningButton"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.unmatchedTarget) {
    const trackOptions = state.trackFolderOptions.map((folder) => ({ value: folder, label: folder }));
    const carOptions = state.uploadCarOptions.map((c) => ({ value: c.name, label: c.name, carClass: c.carClass }));
    const items = state.unmatchedTarget.items;
    const total = items.length;
    // Clamped defensively; currentIndex only ever moves within [0, total-1]
    // via prev/next/goto/save below, so this is a no-op in practice.
    const idx = Math.max(0, Math.min(state.unmatchedTarget.currentIndex, total - 1));
    const item = items[idx];
    const isTrack = item.kind === "track";
    const fieldLabel = t(isTrack ? "manualUploadTrackLabel" : "manualUploadCarLabel");

    // Each step is exactly one distinct unmatched track OR car value - never
    // both at once, since a single mapping already fixes every setup that
    // shared it, and mixing the two kinds in one step would just re-create
    // the per-setup pairing this dialog moved away from.
    const fieldHtml = `
          <div class="field">
            <label>${escapeHtml(fieldLabel)}</label>
            ${renderSearchableSelect({
              id: `unmatched-field-${idx}`,
              options: isTrack ? trackOptions : carOptions,
              selected: item.selected,
              placeholder: t(isTrack ? "manualUploadTrackPlaceholder" : "manualUploadCarPlaceholder"),
              withLogos: !isTrack,
              clearable: true,
            })}
          </div>`;

    const rowHtml = `
      <div class="card elev-sm">
        <div class="unmatched-identified">
          <div>${escapeHtml(fieldLabel)}: <strong>${escapeHtml(item.name)}</strong></div>
        </div>
        ${fieldHtml}
        <div class="dialog-actions" style="margin-top:0;">
          <button type="button" class="btn btn-ghost" id="unmatched-item-next" ${idx === total - 1 ? "disabled" : ""}>
            ${escapeHtml(t("unmatchedNextButton"))}
          </button>
        </div>
      </div>
    `;

    // Stepper: one dot per unmatched track/car value, so a step can be
    // jumped to directly instead of only walking through prev/next - ringed
    // when current, so progress stays visible at a glance even for a long
    // list. There's no per-item "saved" state to show: saving happens in one
    // batch at the bottom (see unmatched-save-close/unmatched-save-rerun
    // below), which closes the dialog immediately, so a dot never needs to
    // reflect it.
    const dotsHtml = items
      .map((it, i) => `<button type="button" class="unmatched-stepper-dot ${i === idx ? "active" : ""}" data-unmatched-goto="${i}" title="${escapeHtml(it.name)}"></button>`)
      .join("");

    html += `
      <div class="dialog-backdrop" data-modal="unmatched">
        <div class="dialog elev-lg" style="width: min(560px, 100%);">
          <div class="dialog-title">${ICONS.warning}${escapeHtml(t("unmatchedDialogTitle"))}</div>
          <div class="dialog-body">
            <p>${escapeHtml(t("unmatchedDialogIntro"))}</p>
            <div style="margin-top: var(--space-2);">
              ${rowHtml}
            </div>
            <div class="unmatched-stepper">
              <button type="button" class="btn btn-ghost" id="unmatched-prev" ${idx === 0 ? "disabled" : ""}>
                <span style="display:inline-flex; transform:rotate(180deg);">${ICONS.chevron}</span>
              </button>
              <div class="unmatched-stepper-dots">${dotsHtml}</div>
              <button type="button" class="btn btn-ghost" id="unmatched-next" ${idx === total - 1 ? "disabled" : ""}>${ICONS.chevron}</button>
            </div>
            <p class="unmatched-stepper-progress">${tFn("unmatchedStepperProgress", idx + 1, total)}</p>
          </div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-secondary" id="unmatched-cancel">${escapeHtml(t("mapFolderCancel"))}</button>
            <button type="button" class="btn btn-secondary" id="unmatched-copy" style="margin-left:auto;">${ICONS.copy}${escapeHtml(t("unmatchedCopyButton"))}</button>
            <button type="button" class="btn btn-secondary" id="unmatched-save-close">${escapeHtml(t("unmatchedSaveCloseButton"))}</button>
            <button type="button" class="btn btn-primary" id="unmatched-save-rerun">${escapeHtml(t("unmatchedSaveRerunButton"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.deleteTarget) {
    const deleteTitle = state.deleteTarget.allInstalled
      ? t("deleteAllInstalledConfirmTitle")
      : state.deleteTarget.all
      ? t("deleteAllConfirmTitle")
      : t("deleteConfirmTitle");
    const deleteBody = state.deleteTarget.allInstalled
      ? tFn("deleteAllInstalledConfirmBody", state.installedData.grandTotal)
      : state.deleteTarget.groupType
      ? tFn("deleteGroupConfirmBody", state.deleteTarget.groupType, state.deleteTarget.car, state.deleteTarget.setupIds.length)
      : state.deleteTarget.all
      ? tFn("deleteAllConfirmBody", state.deleteTarget.track, state.deleteTarget.setupIds.length)
      : tFn("deleteConfirmBody", state.deleteTarget.car, state.deleteTarget.track);
    html += `
      <div class="dialog-backdrop" data-modal="delete-confirm">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.warning}${escapeHtml(deleteTitle)}</div>
          <div class="dialog-body">${escapeHtml(deleteBody)}</div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="delete-cancel">${escapeHtml(t("deleteConfirmCancel"))}</button>
            <button type="button" class="btn btn-danger" id="delete-confirm">${escapeHtml(t("deleteConfirmConfirm"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.mappingDeleteTarget) {
    const mappingDeleteTitle =
      state.mappingDeleteTarget.kind === "all" ? t("mappingDeleteAllConfirmTitle") : t("mappingDeleteConfirmTitle");
    const mappingDeleteBody =
      state.mappingDeleteTarget.kind === "all"
        ? tFn("mappingDeleteAllConfirmBody", state.manualMappings.length)
        : tFn("mappingDeleteConfirmBody", state.mappingDeleteTarget.name);
    html += `
      <div class="dialog-backdrop" data-modal="mapping-delete-confirm">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.warning}${escapeHtml(mappingDeleteTitle)}</div>
          <div class="dialog-body">${escapeHtml(mappingDeleteBody)}</div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="mapping-delete-cancel">${escapeHtml(t("deleteConfirmCancel"))}</button>
            <button type="button" class="btn btn-danger" id="mapping-delete-confirm">${escapeHtml(t("deleteConfirmConfirm"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.dangerTarget) {
    if (state.dangerBusy) {
      const busyTitle = state.dangerTarget.kind !== "dropbox"
        ? t("dangerBusyTitle")
        : state.dangerPhase === "cleaning_folders"
        ? t("dangerCleanupFoldersProgress")
        : tFn("dangerCleanupProgress", state.dangerDeletedCount);
      html += `
        <div class="dialog-backdrop" data-modal="danger-busy">
          <div class="dialog elev-lg" style="width: min(560px, 100%);">
            <div style="display:flex; align-items:center; gap:10px;">
              <div class="spinner"></div>
              <div class="dialog-title" style="margin:0;">${escapeHtml(busyTitle)}</div>
            </div>
          </div>
        </div>
      `;
    } else {
      const isDropbox = state.dangerTarget.kind === "dropbox";
      const dangerTitle = isDropbox ? t("dangerConfirmSetupsTitle") : t("dangerConfirmAllTitle");
      const dangerBody = isDropbox ? t("dangerConfirmSetupsBody") : t("dangerConfirmAllBody");
      const dangerConfirmLabel = state.dangerCountdown > 0 ? tFn("dangerConfirmWaitLabel", state.dangerCountdown) : t("dangerConfirmButton");
      html += `
        <div class="dialog-backdrop" data-modal="danger-confirm">
          <div class="dialog elev-lg">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:2px;">
              ${ICONS.warning}
              <div class="dialog-title" style="margin:0; color:var(--color-danger);">${escapeHtml(dangerTitle)}</div>
            </div>
            <div class="dialog-body">${escapeHtml(dangerBody)}</div>
            <div class="dialog-actions">
              <button type="button" class="btn btn-ghost" id="danger-cancel">${escapeHtml(t("deleteConfirmCancel"))}</button>
              <button type="button" class="btn btn-danger" id="danger-confirm" ${state.dangerCountdown > 0 ? "disabled" : ""}>${escapeHtml(dangerConfirmLabel)}</button>
            </div>
          </div>
        </div>
      `;
    }
  }

  if (state.dropboxOAuth && state.dropboxOAuth.step === "choice") {
    html += `
      <div class="dialog-backdrop" data-modal="dropbox-oauth-choice">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.externalLink}${escapeHtml(t("dropboxOauthChoiceTitle"))}</div>
          <div class="dialog-body">
            <p class="token-choice-warning">${ICONS.fieldWarning}${escapeHtml(t("dropboxOauthChoiceWarning"))}</p>
            <div class="token-choice-list">
              <button type="button" class="mode-card" id="dropbox-oauth-choice-read-write">
                <h3>${escapeHtml(t("dropboxOauthReadWriteTitle"))}</h3>
                <p>${escapeHtml(t("dropboxOauthReadWriteDesc"))}</p>
              </button>
              <button type="button" class="mode-card" id="dropbox-oauth-choice-read-only">
                <h3>${escapeHtml(t("dropboxOauthReadOnlyTitle"))}</h3>
                <p>${escapeHtml(t("dropboxOauthReadOnlyDesc"))}</p>
              </button>
            </div>
          </div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="dropbox-oauth-choice-cancel">${escapeHtml(t("mapFolderCancel"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.dropboxOAuth && state.dropboxOAuth.step === "code") {
    html += `
      <div class="dialog-backdrop" data-modal="dropbox-oauth">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.externalLink}${escapeHtml(t("dropboxOauthDialogTitle"))}</div>
          <div class="dialog-body">
            ${escapeHtml(t("dropboxOauthDialogBody"))}
            <input class="input" id="dropbox-oauth-code-input" style="margin-top:12px;" placeholder="${escapeHtml(t("dropboxOauthCodePlaceholder"))}">
          </div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="dropbox-oauth-cancel">${escapeHtml(t("mapFolderCancel"))}</button>
            <button type="button" class="btn btn-primary" id="dropbox-oauth-confirm">${escapeHtml(t("mapConfirm"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.tracktitanFetch) {
    html += `
      <div class="dialog-backdrop" data-modal="tracktitan-fetch">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.externalLink}${escapeHtml(t("tracktitanFetchDialogTitle"))}</div>
          <div class="dialog-body">${escapeHtml(t("tracktitanFetchDialogBody"))}</div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="tracktitan-fetch-cancel">${escapeHtml(t("mapFolderCancel"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.unsavedChangesPrompt) {
    html += `
      <div class="dialog-backdrop" data-modal="unsaved-changes">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.warning}${escapeHtml(t("unsavedChangesTitle"))}</div>
          <div class="dialog-body">${escapeHtml(t("unsavedChangesBody"))}</div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="unsaved-cancel" style="margin-right:auto;">${escapeHtml(t("mapFolderCancel"))}</button>
            <button type="button" class="btn btn-secondary" id="unsaved-discard">${escapeHtml(t("unsavedChangesDiscard"))}</button>
            <button type="button" class="btn btn-primary" id="unsaved-save">${escapeHtml(t("unsavedChangesSave"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.validationErrors) {
    html += `
      <div class="dialog-backdrop" data-modal="validation">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.validation}${escapeHtml(t("validationTitle"))}</div>
          <div class="dialog-body">${validationBody(state.validationErrors, state.selectedMode)}</div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="validation-cancel">${escapeHtml(t("validationClose"))}</button>
            <button type="button" class="btn btn-primary" id="validation-settings">${escapeHtml(t("validationGoSettings"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  // Same shape as the validation dialog above (title icon + close/go-to-settings
  // actions), triggered instead by a 403/401 surfaced mid-run as an AuthError -
  // see window.onProgress.
  if (state.authErrorCode) {
    html += `
      <div class="dialog-backdrop" data-modal="auth-error">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.validation}${escapeHtml(t("authErrorTitle"))}</div>
          <div class="dialog-body">${escapeHtml(authErrorBody(state.authErrorCode, state.authErrorStatus))}</div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="auth-error-cancel">${escapeHtml(t("validationClose"))}</button>
            <button type="button" class="btn btn-primary" id="auth-error-settings">${escapeHtml(t("validationGoSettings"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  root.innerHTML = html;

  const warningDismiss = document.getElementById("warning-dismiss");
  if (warningDismiss) {
    warningDismiss.addEventListener("click", async () => {
      state.showWarning = false;
      renderModals();
      await api().dismiss_hymo_warning();
    });
  }

  if (state.unmatchedTarget) {
    const unmatchedIdx = Math.max(0, Math.min(state.unmatchedTarget.currentIndex, state.unmatchedTarget.items.length - 1));
    // Only the current step's single select exists in the DOM -
    // bindSearchableSelect no-ops on an id it can't find.
    bindSearchableSelect(root, `unmatched-field-${unmatchedIdx}`, (value) => { state.unmatchedTarget.items[unmatchedIdx].selected = value; }, renderModals);

    const unmatchedItemNext = document.getElementById("unmatched-item-next");
    if (unmatchedItemNext) {
      unmatchedItemNext.addEventListener("click", () => {
        if (state.unmatchedTarget.currentIndex < state.unmatchedTarget.items.length - 1) state.unmatchedTarget.currentIndex += 1;
        renderModals();
      });
    }

    const unmatchedPrev = document.getElementById("unmatched-prev");
    if (unmatchedPrev) {
      unmatchedPrev.addEventListener("click", () => {
        if (state.unmatchedTarget.currentIndex > 0) state.unmatchedTarget.currentIndex -= 1;
        renderModals();
      });
    }

    const unmatchedNext = document.getElementById("unmatched-next");
    if (unmatchedNext) {
      unmatchedNext.addEventListener("click", () => {
        if (state.unmatchedTarget.currentIndex < state.unmatchedTarget.items.length - 1) state.unmatchedTarget.currentIndex += 1;
        renderModals();
      });
    }

    root.querySelectorAll("[data-unmatched-goto]").forEach((dot) => {
      dot.addEventListener("click", () => {
        state.unmatchedTarget.currentIndex = Number(dot.dataset.unmatchedGoto);
        renderModals();
      });
    });

    const unmatchedCopy = document.getElementById("unmatched-copy");
    if (unmatchedCopy) {
      unmatchedCopy.addEventListener("click", async () => {
        // items is already deduped (see openUnmatchedModal) - just split back
        // into the two kinds for the copy text.
        const tracks = state.unmatchedTarget.items.filter((it) => it.kind === "track").map((it) => it.name).sort();
        const cars = state.unmatchedTarget.items.filter((it) => it.kind === "car").map((it) => it.name).sort();
        const sections = [];
        if (tracks.length) sections.push(`${t("unmatchedCopyTracksLabel")}\n${tracks.join("\n")}`);
        if (cars.length) sections.push(`${t("unmatchedCopyCarsLabel")}\n${cars.join("\n")}`);
        await copyTextToClipboard(sections.join("\n\n"));
        showToast(t("copiedToast"), "success");
      });
    }

    const unmatchedCancel = document.getElementById("unmatched-cancel");
    if (unmatchedCancel) {
      unmatchedCancel.addEventListener("click", () => {
        // No api call and no rerun: discards every selection made in this
        // dialog and simply closes it, leaving all setups unmatched.
        state.unmatchedTarget = null;
        renderModals();
      });
    }

    const unmatchedSaveClose = document.getElementById("unmatched-save-close");
    const unmatchedSaveRerun = document.getElementById("unmatched-save-rerun");
    if (unmatchedSaveClose && unmatchedSaveRerun) {
      unmatchedSaveClose.addEventListener("click", async () => {
        unmatchedSaveClose.disabled = true;
        unmatchedSaveRerun.disabled = true;
        await saveAllUnmatchedMappings();
        state.unmatchedTarget = null;
        renderModals();
      });
      unmatchedSaveRerun.addEventListener("click", async () => {
        unmatchedSaveClose.disabled = true;
        unmatchedSaveRerun.disabled = true;
        await saveAllUnmatchedMappings();
        state.unmatchedTarget = null;
        renderModals();
        // Re-run the same mode's download/upload now that the mappings that
        // resolve these items are in place, so the freshly-mapped setups get
        // picked up without the user having to go find the Start button.
        await startRun();
      });
    }
  }

  const deleteCancel = document.getElementById("delete-cancel");
  if (deleteCancel) {
    deleteCancel.addEventListener("click", () => {
      state.deleteTarget = null;
      renderModals();
    });
  }

  const deleteConfirm = document.getElementById("delete-confirm");
  if (deleteConfirm) {
    deleteConfirm.addEventListener("click", async () => {
      const { setupIds, all, allInstalled } = state.deleteTarget;
      state.deleteTarget = null;
      renderModals();
      if (allInstalled) {
        await api().delete_all_setups();
      } else if (all) {
        await api().delete_setups(setupIds);
      } else {
        await api().delete_setup(setupIds[0]);
      }
      await refreshInstalled();
      renderSetupsView();
      renderSidebar();
      showToast(t(allInstalled ? "deletedAllInstalledToast" : all ? "deletedAllToast" : "deletedToast"), "success");
    });
  }

  const mappingDeleteCancel = document.getElementById("mapping-delete-cancel");
  if (mappingDeleteCancel) {
    mappingDeleteCancel.addEventListener("click", () => {
      state.mappingDeleteTarget = null;
      renderModals();
    });
  }

  const mappingDeleteConfirm = document.getElementById("mapping-delete-confirm");
  if (mappingDeleteConfirm) {
    mappingDeleteConfirm.addEventListener("click", async () => {
      const target = state.mappingDeleteTarget;
      state.mappingDeleteTarget = null;
      renderModals();
      if (target.kind === "all") {
        await api().delete_all_manual_mappings();
      } else {
        await api().delete_manual_mapping(target.id);
      }
      await refreshMappings();
      renderMappingView();
      showToast(t(target.kind === "all" ? "mappingDeletedAllToast" : "mappingDeletedToast"), "success");
    });
  }

  const dangerCancel = document.getElementById("danger-cancel");
  if (dangerCancel) {
    dangerCancel.addEventListener("click", cancelDangerConfirm);
  }

  const dangerConfirm = document.getElementById("danger-confirm");
  if (dangerConfirm) {
    dangerConfirm.addEventListener("click", confirmDangerAction);
  }

  const dropboxOauthChoiceCancel = document.getElementById("dropbox-oauth-choice-cancel");
  if (dropboxOauthChoiceCancel) {
    dropboxOauthChoiceCancel.addEventListener("click", () => {
      state.dropboxOAuth = null;
      renderModals();
    });
  }

  const dropboxOauthChoiceReadWrite = document.getElementById("dropbox-oauth-choice-read-write");
  if (dropboxOauthChoiceReadWrite) {
    dropboxOauthChoiceReadWrite.addEventListener("click", () => startDropboxOauthFlow("read_write"));
  }

  const dropboxOauthChoiceReadOnly = document.getElementById("dropbox-oauth-choice-read-only");
  if (dropboxOauthChoiceReadOnly) {
    dropboxOauthChoiceReadOnly.addEventListener("click", () => startDropboxOauthFlow("read_only"));
  }

  const dropboxOauthCancel = document.getElementById("dropbox-oauth-cancel");
  if (dropboxOauthCancel) {
    dropboxOauthCancel.addEventListener("click", () => {
      state.dropboxOAuth = null;
      renderModals();
    });
  }

  const dropboxOauthConfirm = document.getElementById("dropbox-oauth-confirm");
  if (dropboxOauthConfirm) {
    dropboxOauthConfirm.addEventListener("click", async () => {
      const code = document.getElementById("dropbox-oauth-code-input").value.trim();
      if (!code) return;
      const { appKey, appSecret } = state.dropboxOAuth;
      const result = await api().dropbox_oauth_exchange_code(appKey, appSecret, code);
      if (!result || result.error) {
        showToast((result && result.error) || t("dropboxOauthGenericError"), "error");
        return;
      }
      state.dropboxOAuth = null;
      renderModals();
      const tokenInput = document.getElementById("f-DROPBOX_REFRESH_TOKEN");
      if (tokenInput) tokenInput.value = result.refreshToken;
      await persistSettings();
      showToast(t("dropboxOauthSuccessToast"), "success");
    });
  }

  const unsavedCancel = document.getElementById("unsaved-cancel");
  if (unsavedCancel) {
    unsavedCancel.addEventListener("click", () => resolveUnsavedChangesPrompt("cancel"));
  }

  const unsavedDiscard = document.getElementById("unsaved-discard");
  if (unsavedDiscard) {
    unsavedDiscard.addEventListener("click", () => resolveUnsavedChangesPrompt("discard"));
  }

  const unsavedSave = document.getElementById("unsaved-save");
  if (unsavedSave) {
    unsavedSave.addEventListener("click", () => resolveUnsavedChangesPrompt("save"));
  }

  const tracktitanFetchCancel = document.getElementById("tracktitan-fetch-cancel");
  if (tracktitanFetchCancel) {
    tracktitanFetchCancel.addEventListener("click", async () => {
      state.tracktitanFetch = null;
      renderModals();
      await api().tracktitan_fetch_tokens_cancel();
    });
  }

  const validationCancel = document.getElementById("validation-cancel");
  if (validationCancel) {
    validationCancel.addEventListener("click", () => {
      state.validationErrors = null;
      renderModals();
    });
  }

  const validationSettings = document.getElementById("validation-settings");
  if (validationSettings) {
    validationSettings.addEventListener("click", () => {
      state.validationErrors = null;
      renderModals();
      state.view = "settings";
      applyActiveView();
    });
  }

  const authErrorCancel = document.getElementById("auth-error-cancel");
  if (authErrorCancel) {
    authErrorCancel.addEventListener("click", () => {
      state.authErrorCode = null;
      state.authErrorStatus = null;
      renderModals();
    });
  }

  const authErrorSettings = document.getElementById("auth-error-settings");
  if (authErrorSettings) {
    authErrorSettings.addEventListener("click", () => {
      state.authErrorCode = null;
      state.authErrorStatus = null;
      renderModals();
      state.view = "settings";
      applyActiveView();
    });
  }
}

// Resolves the unsaved-changes prompt raised by either the nav guard (leaving
// Settings) or window.onRequestCloseConfirmation (closing the app). "cancel"
// just dismisses it and leaves the user where they were; "save"/"discard"
// resolve the form first, then carry out whichever action was pending.
async function resolveUnsavedChangesPrompt(action) {
  const prompt = state.unsavedChangesPrompt;
  state.unsavedChangesPrompt = null;
  renderModals();
  if (action === "save") await persistSettings();
  else if (action === "discard") await discardSettingsChanges();
  if (!prompt || action === "cancel") return;
  if (prompt.reason === "nav") goToView(prompt.target);
  else if (prompt.reason === "close") await api().confirm_close();
}

// ----- custom text-field context menu (Cut/Copy/Paste/Select all) --------------
// pywebview's EdgeChromium backend ties the native right-click context menu to
// debug mode (AreDefaultContextMenusEnabled = debug), and this app never runs
// with debug=True in production - so right-clicking anywhere, including inside
// a text/password field, normally shows nothing at all. Rather than turning on
// debug mode (which would also expose DevTools/Inspect to end users), this
// renders a small menu of our own for editable fields, wired through the same
// clipboard APIs the Settings "copy" button already uses.

// Only input types the Selection API (selectionStart/selectionEnd/setRangeText)
// actually supports - per the HTML spec, "number" and similar non-text types
// throw when read/written this way, so they are deliberately left out (Ctrl+C/
// Ctrl+V on those still work natively; this menu just doesn't cover them).
const EDITABLE_TEXT_INPUT_TYPES = new Set(["text", "search", "url", "tel", "password"]);

let contextMenuEl = null;

function closeContextMenu() {
  if (contextMenuEl) {
    contextMenuEl.remove();
    contextMenuEl = null;
  }
}

function getEditableTextField(el) {
  const field = el.closest("input");
  if (!field || field.disabled) return null;
  return EDITABLE_TEXT_INPUT_TYPES.has(field.type) ? field : null;
}

// Shared with the Settings "copy" button's own fallback: the async Clipboard
// API is preferred, but falls back to a hidden textarea + execCommand for
// hosts where it is unavailable (rather than the field itself, since the
// field may be masked or the text may be only part of its value). Paste does
// NOT use this - see contextMenuPaste's comment for why reading is different
// from writing here.
async function copyTextToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch (e) {
    // fall through to the legacy path below
  }
  const helper = document.createElement("textarea");
  helper.value = text;
  helper.style.position = "fixed";
  helper.style.opacity = "0";
  document.body.appendChild(helper);
  helper.select();
  document.execCommand("copy");
  helper.remove();
}

async function contextMenuCut(field) {
  const start = field.selectionStart, end = field.selectionEnd;
  const selected = field.value.slice(start, end);
  if (!selected) return;
  await copyTextToClipboard(selected);
  field.setRangeText("", start, end, "end");
  field.dispatchEvent(new Event("input", { bubbles: true }));
}

async function contextMenuCopy(field) {
  const selected = field.value.slice(field.selectionStart, field.selectionEnd);
  if (selected) await copyTextToClipboard(selected);
}

// Paste can't use navigator.clipboard.readText() the way copy/cut use
// writeText(): reading is blocked here without a permission grant WebView2
// never prompts for in this app, and the legacy document.execCommand("paste")
// fallback that used to sit here is a documented WebView2 bug - it can
// silently insert the wrong content (e.g. the app's own local URL) instead of
// a real paste (MicrosoftEdge/WebView2Feedback#1945). Physical Ctrl+V has
// always worked correctly because it never goes through either JS API - it's
// handled natively by WebView2 as a real OS keystroke. So instead of reading
// the clipboard in JS, this asks Python to synthesize that same real,
// OS-level Ctrl+V keystroke (see Api.simulate_paste_shortcut): WebView2 can't
// tell it apart from the user physically pressing the keys, so it goes
// through the exact path that already works.
async function contextMenuPaste(field) {
  field.focus();
  try {
    await api().simulate_paste_shortcut();
  } catch (e) {
    showToast(t("clipboardPasteBlockedToast"), "error");
  }
}

function contextMenuSelectAll(field) {
  field.focus();
  field.select();
}

function openContextMenu(e, field) {
  closeContextMenu();
  field.focus();

  const hasSelection = field.selectionStart !== field.selectionEnd;
  const items = [
    { key: "cut", label: t("contextMenuCut"), enabled: hasSelection && !field.readOnly, run: () => contextMenuCut(field) },
    { key: "copy", label: t("contextMenuCopy"), enabled: hasSelection, run: () => contextMenuCopy(field) },
    { key: "paste", label: t("contextMenuPaste"), enabled: !field.readOnly, run: () => contextMenuPaste(field) },
    { key: "selectAll", label: t("contextMenuSelectAll"), enabled: !!field.value, run: () => contextMenuSelectAll(field) },
  ];

  const menu = document.createElement("div");
  menu.className = "context-menu";
  menu.innerHTML = items
    .map((i) => `<button type="button" class="context-menu-item" data-key="${i.key}" ${i.enabled ? "" : "disabled"}>${escapeHtml(i.label)}</button>`)
    .join("");
  document.body.appendChild(menu);
  contextMenuEl = menu;

  // Clamp inside the viewport (fixed positioning, so this is viewport-relative
  // regardless of any scrolled container underneath) so a right-click near the
  // window edge doesn't open the menu partially off-screen.
  const rect = menu.getBoundingClientRect();
  const x = Math.max(4, Math.min(e.clientX, window.innerWidth - rect.width - 4));
  const y = Math.max(4, Math.min(e.clientY, window.innerHeight - rect.height - 4));
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;

  items.forEach((item) => {
    if (!item.enabled) return;
    menu.querySelector(`[data-key="${item.key}"]`).addEventListener("click", async () => {
      closeContextMenu();
      await item.run();
    });
  });
}

document.addEventListener("contextmenu", (e) => {
  const field = getEditableTextField(e.target);
  if (!field) {
    closeContextMenu();
    return;
  }
  e.preventDefault();
  openContextMenu(e, field);
});

document.addEventListener("mousedown", (e) => {
  if (contextMenuEl && !contextMenuEl.contains(e.target)) closeContextMenu();
});
document.addEventListener("scroll", closeContextMenu, true);
window.addEventListener("blur", closeContextMenu);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeContextMenu();
});

// ----- global delegated handlers (survive re-renders) --------------------------

document.addEventListener("click", (e) => {
  const link = e.target.closest("[data-open-link]");
  if (link) {
    e.preventDefault();
    api().open_external_link(link.dataset.openLink);
  }
});

// Mirrors Settings' dirty state to Python on every edit, scoped to the
// Settings view so typing elsewhere (search boxes, dialog inputs) doesn't
// trigger a needless IPC round trip - see pushSettingsDirty().
function onSettingsFieldChanged(e) {
  if (e.target.closest("#view-settings")) pushSettingsDirty();
}
document.addEventListener("input", onSettingsFieldChanged);
document.addEventListener("change", onSettingsFieldChanged);

window.addEventListener("DOMContentLoaded", init);
