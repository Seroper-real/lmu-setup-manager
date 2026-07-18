// HYMO Dashboard frontend. Vanilla JS, no framework, no build step.
// Full-innerHTML replace per render() call, per view. window.pywebview.api.* is
// the only bridge into Python; window.onProgress is Python's push channel back.

const state = {
  view: "setups",
  language: "it",
  bootstrap: null,
  selectedMode: "full",
  showSecrets: false,
  advancedOpen: false,
  running: false,
  runStatus: "idle", // idle | running | completed | stopped | error
  activity: [],
  installedSearch: "",
  installedUnmappedOnly: false,
  installedData: { groups: [], totalCount: 0, grandTotal: 0 },
  // Track cards default to collapsed (perf: >400 setups rendered fully expanded
  // was the main source of startup jank) and open on user click; the Set holds
  // manually-expanded track keys. A non-empty search force-expands every card
  // regardless of this set, without mutating it, so clearing the search restores
  // the manual state exactly as the user left it.
  expandedTracks: new Set(),
  // Per-car accordion inside an expanded track card, keyed by setupId - reveals
  // that car's individual installed setup file names on click.
  expandedCars: new Set(),
  trackFolderOptions: [],
  correggiTarget: null,
  deleteTarget: null,
  dropboxOAuth: null,
  validationErrors: null,
  authErrorMessage: null,
  showWarning: false,
  settingsForm: null,
};

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
  navSettings: `<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"></circle><path d="M12 3.5v2.4M12 18.1v2.4M4.9 6.3l1.7 1.7M17.4 16l1.7 1.7M3.5 12H6M18 12h2.5M4.9 17.7l1.7-1.7M17.4 8l1.7-1.7"></path></svg>`,
  search: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-neutral-500)" stroke-width="2" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="M20 20l-4.35-4.35"></path></svg>`,
  filter: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16l-6 8v6l-4 2v-8Z"></path></svg>`,
  chevron: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"></path></svg>`,
  edit: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path><path d="M14.5 5.5l3 3"></path></svg>`,
  folder: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"></path></svg>`,
  folderBrowse: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"></path></svg>`,
  hotlap: `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.6A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8ZM9.6 15.5v-7l6.3 3.5-6.3 3.5Z"></path></svg>`,
  eyeOpen: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12s3.5-7 9-7 9 7 9 7-3.5 7-9 7-9-7-9-7Z"></path><circle cx="12" cy="12" r="2.6"></circle></svg>`,
  eyeClosed: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3l18 18M10.6 10.7a2.6 2.6 0 0 0 3.6 3.6M6.6 6.7C4.5 8 3 12 3 12s3.5 7 9 7c1.6 0 3-.5 4.2-1.2M9.9 5.2A9.8 9.8 0 0 1 12 5c5.5 0 9 7 9 7a13.7 13.7 0 0 1-2.4 3.3"></path></svg>`,
  externalLink: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3"></path><path d="M14 4h6v6"></path><path d="M10 14 20 4"></path></svg>`,
  info: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><line x1="12" y1="11" x2="12" y2="16.5"></line><circle cx="12" cy="7.6" r="0.4" fill="currentColor"></circle></svg>`,
  save: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h11l3 3v13H5z"></path><path d="M8 4v5h8V4M8 20v-6h8v6"></path></svg>`,
  trash: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"></path><path d="M9 7V4h6v3"></path><path d="M6 7l1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"></path></svg>`,
  copy: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="13" height="13" rx="2"></rect><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path></svg>`,
  play: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4.5v15l13-7.5Z"></path></svg>`,
  stop: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>`,
  activityStopped: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"></circle><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"></path></svg>`,
  activityError: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 7.5v6"></path><circle cx="12" cy="16.7" r="0.6" fill="currentColor"></circle></svg>`,
  warning: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent-300)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5 22 20.5H2Z"></path><path d="M12 10v4.5"></path><circle cx="12" cy="17.5" r="0.6" fill="var(--color-accent-300)"></circle></svg>`,
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
// (mapSavedMessage, summaryRunning, deleteConfirmBody, ...) directly, the same
// fallback order t() uses for plain string keys.
function tFn(key, ...args) {
  const dict = TRANSLATIONS[state.language] || TRANSLATIONS.it;
  if (key in dict) return dict[key](...args);
  const extra = EXTRA[state.language] || EXTRA.it;
  return extra[key](...args);
}

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
  const remoteTracks = cfg.remote_tracks || {};
  const dropbox = cfg.dropbox || {};

  return {
    lmuPath: bootstrap.lmuPath || "",
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
    await refreshInstalled();
  } catch (e) {
    console.error("Failed to load bootstrap", e);
  }
  render();
}

async function refreshInstalled() {
  state.installedData = await api().list_installed_setups(state.installedSearch, state.installedUnmappedOnly);
}

// ----- progress push channel (Python -> JS) -----------------------------------

window.onProgress = function onProgress(event) {
  state.activity.push(event);
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
      state.authErrorMessage = event.title;
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
};

// ----- top-level render ---------------------------------------------------

function render() {
  renderSidebar();
  renderSetupsView();
  renderDownloadView();
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

// ----- sidebar --------------------------------------------------------------

function renderSidebar() {
  document.getElementById("logo-sub").textContent = "Setup Manager";

  const nav = document.getElementById("nav");
  const items = [
    { view: "setups", icon: ICONS.navSetups, label: t("navSetups") },
    { view: "download", icon: ICONS.navDownload, label: t("navDownload") },
    { view: "settings", icon: ICONS.navSettings, label: t("navSettings") },
  ];
  nav.innerHTML = items
    .map(
      (i) => `
        <button class="nav-item" data-view="${i.view}">
          <span class="nav-icon">${i.icon}</span><span>${escapeHtml(i.label)}</span>
        </button>
      `
    )
    .join("");
  nav.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.view = btn.dataset.view;
      applyActiveView();
      // applyActiveView() only toggles which view is visible - it never
      // re-renders one, so navigating to Setups showed whatever was last
      // rendered there (e.g. still empty from init(), or missing setups
      // installed by a run watched from the Download tab). Refresh from the
      // DB on every visit so newly installed setups show up immediately.
      if (state.view === "setups") {
        refreshInstalled().then(() => {
          renderSetupsView();
          renderSidebar();
        });
      }
    });
  });

  // state.selectedMode is the single source of truth for the current mode: it's
  // seeded from bootstrap.mode at init() and kept in sync on every mode-card
  // click via set_mode() (see renderDownloadView). Reading state.bootstrap.mode
  // here instead would freeze the badge at whatever mode the app started in,
  // since bootstrap is only fetched once - the bug this fixes.
  document.getElementById("mode-badge").innerHTML = `
    <span>${escapeHtml(t("sidebarMode"))}</span>
    <span class="tag tag-accent">${escapeHtml((state.selectedMode || "").toUpperCase())}</span>
    ${state.bootstrap && state.bootstrap.sandboxActive ? `<span class="tag tag-warning">SANDBOX</span>` : ""}
  `;

  document.getElementById("installed-count").innerHTML = `
    <span>${escapeHtml(t("sidebarInstalled"))}</span>
    <strong>${state.installedData.grandTotal}</strong>
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
      <button type="button" class="toggle-chip ${state.installedUnmappedOnly ? "active" : ""}" id="setups-unmapped-toggle">${ICONS.filter}${escapeHtml(t("unmappedOnlyFilter"))}</button>
      <span class="tag tag-outline results-count">${state.installedData.totalCount} ${escapeHtml(t("resultsWord"))}</span>
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
      });
    }, 250)
  );

  document.getElementById("setups-unmapped-toggle").addEventListener("click", () => {
    state.installedUnmappedOnly = !state.installedUnmappedOnly;
    refreshInstalled().then(() => {
      renderSetupsView();
      renderSidebar();
    });
  });

  el.querySelectorAll("[data-correggi]").forEach((btn) => {
    btn.addEventListener("click", () => openCorreggiModal(btn.dataset.correggi));
  });

  el.querySelectorAll("[data-toggle-track]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.toggleTrack;
      if (state.expandedTracks.has(key)) state.expandedTracks.delete(key);
      else state.expandedTracks.add(key);
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

  const rows = group.setups.map((s) => renderCarRow(s, group)).join("");
  const setupIds = group.setups.map((s) => s.setupId);

  const unmappedTag = !group.trackFound
    ? `<span class="tag tag-neutral">${escapeHtml(t("unmappedTag"))}</span>
       <button type="button" class="btn btn-ghost" data-correggi="${escapeHtml(group.track)}">${ICONS.edit}${escapeHtml(t("correctButton"))}</button>
       <span class="arrow">&rarr; ${escapeHtml((group.setups[0] && group.setups[0].installationFolder) || "")}</span>`
    : "";

  return `
    <div class="card elev-sm setup-track-card">
      <div class="track-group-header">
        <button type="button" class="track-toggle" data-toggle-track="${escapeHtml(group.track)}">
          <span class="chevron ${expanded ? "expanded" : ""}">${ICONS.chevron}</span>
          <h4>${escapeHtml(group.track)}</h4>
        </button>
        <div class="track-group-actions">
          ${unmappedTag}
          <button type="button" class="btn btn-ghost text-danger" data-delete-track="${escapeHtml(group.track)}" data-delete-track-ids="${escapeHtml(JSON.stringify(setupIds))}" title="${escapeHtml(t("deleteAllButton"))}">${ICONS.trash}</button>
          <span class="tag tag-outline group-count">${group.setups.length}</span>
        </div>
      </div>
      ${expanded ? `<div class="setup-rows">${rows}</div>` : ""}
    </div>
  `;
}

// Each car is its own accordion, independent of the track card's own
// expand/collapse: clicking its header reveals the individual setup file names
// installed for it (s.fileNames), instead of just the aggregate file count.
function renderCarRow(s, group) {
  const carExpanded = state.expandedCars.has(s.setupId);

  const files = (s.fileNames || [])
    .map((name) => `<div class="setup-file">${escapeHtml(name)}</div>`)
    .join("");

  return `
    <div class="setup-car">
      <div class="setup-car-header">
        <button type="button" class="setup-car-toggle" data-toggle-car="${escapeHtml(s.setupId)}">
          <span class="chevron ${carExpanded ? "expanded" : ""}">${ICONS.chevron}</span>
          <span class="car">${escapeHtml(s.car)}</span>
        </button>
        <span class="meta">${formatDate(s.installDate)}</span>
        <span class="tag tag-outline">${s.fileCount} ${escapeHtml(t("filesUnit"))}</span>
        ${s.installationFolder ? `<span class="meta meta-icon">${ICONS.folder}${escapeHtml(s.installationFolder)}</span>` : ""}
        ${s.hotlapLink
          ? `<a class="btn btn-ghost" href="#" data-open-link="${escapeHtml(s.hotlapLink)}" title="${escapeHtml(t("hotlapTitle"))}">${ICONS.hotlap}${escapeHtml(t("hotlapLabel"))}</a>`
          : ""}
        <button type="button" class="btn btn-ghost text-danger" data-delete-setup="${escapeHtml(s.setupId)}" data-car="${escapeHtml(s.car)}" data-track="${escapeHtml(group.track)}" title="${escapeHtml(t("deleteButton"))}">${ICONS.trash}</button>
      </div>
      ${carExpanded ? `<div class="setup-files">${files}</div>` : ""}
    </div>
  `;
}

async function openCorreggiModal(track) {
  state.correggiTarget = { track };
  if (!state.trackFolderOptions.length) {
    state.trackFolderOptions = await api().get_track_folder_options();
  }
  renderModals();
}

// ----- Download ---------------------------------------------------------------

function renderDownloadView() {
  const el = document.getElementById("view-download");
  const modes = [
    { key: "full", title: "Full", desc: t("fullDesc") },
    { key: "master", title: "Master", desc: t("masterDesc") },
    { key: "slave", title: "Slave", desc: t("slaveDesc") },
  ];

  const cards = modes
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
        <p>${escapeHtml(t("downloadDescPre"))}<strong>${escapeHtml(state.selectedMode.toUpperCase())}</strong>${escapeHtml(t("downloadDescPost"))}</p>
      </div>
    </div>
    <div>
      <h6 class="text-muted">${escapeHtml(t("modeSectionHeading"))}</h6>
      <div class="card elev-sm mode-cards">${cards}</div>
    </div>
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

  el.querySelectorAll(".mode-card").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.selectedMode = btn.dataset.mode;
      await api().set_mode(state.selectedMode);
      renderDownloadView();
      renderSidebar();
    });
  });

  document.getElementById("start-stop-btn").addEventListener("click", onStartStopClick);

  const log = document.getElementById("activity-log");
  if (log) log.scrollTop = log.scrollHeight;
}

function renderActivityItem(item) {
  const icons = {
    stopped: ICONS.activityStopped,
    error: ICONS.activityError,
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

async function onStartStopClick() {
  if (state.running) {
    await api().stop_download();
    return;
  }

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

// ----- Settings -----------------------------------------------------------

// renderSettingsView() does a full innerHTML replace of the view (same as
// every other render*() in this file), which throws away whatever the user
// typed but hasn't saved yet. Any handler that re-renders the settings view
// without an intervening save (toggle-secrets, advanced-toggle, language)
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
    f.pageSize = getVal("f-pageSize");
    f.timeout = getVal("f-timeout");
    f.minDelay = getVal("f-minDelay");
    f.maxDelay = getVal("f-maxDelay");
    f.cleanDownload = getChecked("f-cleanDownload");
    f.overwrite = getChecked("f-overwrite");
    f.deletePreviousVersion = getChecked("f-deletePreviousVersion");
    f.remoteTracksEnabled = getChecked("f-remoteTracksEnabled");
    f.remoteTracksUrl = getVal("f-remoteTracksUrl");
    f.remoteTracksTimeout = getVal("f-remoteTracksTimeout");
    f.dropboxTimeout = getVal("f-dropboxTimeout");
    f.dropboxUploadWorkers = getVal("f-dropboxUploadWorkers");
  }
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
// treats a type="password" field.
function secretField(id, label, value, type, titleAction) {
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

function renderSettingsView() {
  const el = document.getElementById("view-settings");
  if (!state.settingsForm) {
    el.innerHTML = "";
    return;
  }
  const f = state.settingsForm;
  const secretType = state.showSecrets ? "text" : "password";
  const tokenUrl = readmeUrl(state.language === "en" ? "tracktitan-tokens" : "token-tracktitan");
  const dropboxUrl = readmeUrl(state.language === "en" ? "dropbox-credentials" : "credenziali-dropbox");

  el.innerHTML = `
    <div class="view-header">
      <div>
        <h2>${escapeHtml(t("settingsTitle"))}</h2>
        <p>${escapeHtml(t("settingsDesc"))}</p>
      </div>
      <button type="button" class="btn btn-ghost" id="toggle-secrets">${state.showSecrets ? ICONS.eyeOpen : ICONS.eyeClosed}${escapeHtml(state.showSecrets ? t("hideValues") : t("showValues"))}</button>
    </div>

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
            <button type="button" class="btn btn-secondary" id="browse-btn">${ICONS.folderBrowse}${escapeHtml(t("browseButton"))}</button>
          </div>
        </div>
        <p class="help-text">${escapeHtml(t("lmuHelp"))}</p>
      </div>
    </div>

    <div class="hr"></div>
    <div>
      <h6 class="text-muted">${escapeHtml(t("tokenHeading"))}</h6>
      <p class="text-muted" style="font-size:13px;">${escapeHtml(t("tokenHelp"))}</p>
      ${secretField("f-ACCESS_TOKEN_LIST", displayKey("ACCESS_TOKEN_LIST"), f.env.ACCESS_TOKEN_LIST, secretType)}
      ${secretField("f-ACCESS_TOKEN_DOWNLOAD", displayKey("ACCESS_TOKEN_DOWNLOAD"), f.env.ACCESS_TOKEN_DOWNLOAD, secretType)}
      <div class="field">
        <label>${displayKey("USER_ID")}</label>
        <input class="input" type="text" id="f-USER_ID" value="${escapeHtml(f.env.USER_ID)}">
      </div>
      <a href="#" class="readme-link" data-open-link="${tokenUrl}">${ICONS.externalLink}${escapeHtml(t("tokenLinkText"))}</a>
    </div>

    <div class="hr"></div>
    <div>
      <h6 class="text-muted">${escapeHtml(t("dropboxHeading"))}</h6>
      <p class="text-muted" style="font-size:13px;">${escapeHtml(t("dropboxHelp"))}</p>
      <div class="field">
        <label>${displayKey("DROPBOX_APP_KEY")}</label>
        <input class="input" type="text" id="f-DROPBOX_APP_KEY" value="${escapeHtml(f.env.DROPBOX_APP_KEY)}">
      </div>
      ${secretField("f-DROPBOX_APP_SECRET", displayKey("DROPBOX_APP_SECRET"), f.env.DROPBOX_APP_SECRET, secretType)}
      ${secretField(
        "f-DROPBOX_REFRESH_TOKEN",
        displayKey("DROPBOX_REFRESH_TOKEN"),
        f.env.DROPBOX_REFRESH_TOKEN,
        secretType,
        `<a href="#" class="field-hint-link" id="dropbox-oauth-start-btn">${ICONS.externalLink}${escapeHtml(t("dropboxOauthButton"))}</a>`
      )}
      <div class="field">
        <label>${escapeHtml(t("dropboxFolderLabel"))}</label>
        <input class="input" type="text" id="f-dropboxFolder" value="${escapeHtml(f.dropboxFolder)}">
      </div>
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

    <div>
      <button type="button" class="btn btn-primary" id="save-settings-btn">${ICONS.save}${escapeHtml(t("saveButton"))}</button>
    </div>
  `;

  document.getElementById("toggle-secrets").addEventListener("click", () => {
    captureSettingsForm();
    state.showSecrets = !state.showSecrets;
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
    const result = await api().dropbox_oauth_get_url(appKey, appSecret);
    if (!result || result.error) {
      showToast((result && result.error) || t("dropboxOauthGenericError"), "error");
      return;
    }
    await api().open_external_link(result.url);
    state.dropboxOAuth = { appKey, appSecret };
    renderModals();
  });

  document.getElementById("browse-btn").addEventListener("click", async () => {
    const current = document.getElementById("lmu-path-input").value;
    const picked = await api().browse_lmu_folder(current);
    if (picked) {
      document.getElementById("lmu-path-input").value = picked;
    }
  });

  document.getElementById("advanced-toggle").addEventListener("click", () => {
    captureSettingsForm();
    state.advancedOpen = !state.advancedOpen;
    renderSettingsView();
  });

  document.getElementById("save-settings-btn").addEventListener("click", onSaveSettings);
}

function renderAdvancedFields(f) {
  const textField = (id, labelKey, tipKey, value, type) => `
    <div class="field">
      <label>${escapeHtml(t(labelKey))} ${infoTip(t(tipKey))}</label>
      <input class="input" type="${type || "text"}" id="${id}" value="${escapeHtml(value)}">
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

async function onSaveSettings() {
  const envValues = {
    ACCESS_TOKEN_LIST: getVal("f-ACCESS_TOKEN_LIST"),
    ACCESS_TOKEN_DOWNLOAD: getVal("f-ACCESS_TOKEN_DOWNLOAD"),
    USER_ID: getVal("f-USER_ID"),
    DROPBOX_APP_KEY: getVal("f-DROPBOX_APP_KEY"),
    DROPBOX_APP_SECRET: getVal("f-DROPBOX_APP_SECRET"),
    DROPBOX_REFRESH_TOKEN: getVal("f-DROPBOX_REFRESH_TOKEN"),
  };

  const lmuPath = document.getElementById("lmu-path-input").value;
  const configPatch = {
    paths: {
      setups: {
        lmu_base_path: lmuPath,
        overwrite: getChecked("f-overwrite"),
        delete_previous_version: getChecked("f-deletePreviousVersion"),
      },
      download: {
        clean_download_after_copy: getChecked("f-cleanDownload"),
      },
    },
    dropbox: {
      folder: getVal("f-dropboxFolder"),
    },
  };

  if (state.advancedOpen) {
    configPatch.logging = { level: getVal("f-logLevel") };
    configPatch.network = {
      min_delay: parseFloat(getVal("f-minDelay")),
      max_delay: parseFloat(getVal("f-maxDelay")),
      timeout: parseInt(getVal("f-timeout"), 10),
      page_size: parseInt(getVal("f-pageSize"), 10),
    };
    configPatch.remote_tracks = {
      enabled: getChecked("f-remoteTracksEnabled"),
      url: getVal("f-remoteTracksUrl"),
      timeout: parseInt(getVal("f-remoteTracksTimeout"), 10),
    };
    configPatch.dropbox.timeout = parseInt(getVal("f-dropboxTimeout"), 10);
    configPatch.dropbox.upload_workers = parseInt(getVal("f-dropboxUploadWorkers"), 10);
  }

  await api().save_settings(envValues, configPatch);

  // Settings now hot-reload instead of relaunching the process: re-fetch
  // bootstrap so the form (and the mode badge/sandbox tag, in case anything
  // else changed underneath) reflects exactly what was just persisted.
  state.bootstrap = await api().get_bootstrap();
  state.settingsForm = buildSettingsForm(state.bootstrap);
  renderSettingsView();
  renderSidebar();
  showToast(t("savedToast"), "success");
}

// ----- modals (warning / correggi / validation) --------------------------------

// Our real check_credentials() returns a flat list of missing/invalid field
// names rather than the mock's single validateCredentials() error type, since
// a run can be short on both TrackTitan and Dropbox credentials at once. Pick
// the matching real sentence(s) for whichever family of fields shows up.
function validationBody(errors, mode) {
  const modeLabel = mode.toUpperCase();
  const hasTrackTitan = errors.some((e) => e.includes("ACCESS_TOKEN") || e.includes("USER_ID"));
  const hasDropbox = errors.some((e) => e.includes("DROPBOX"));
  const sentences = [];
  if (hasTrackTitan) sentences.push(tFn("validationMissingTrackTitan", modeLabel));
  if (hasDropbox) sentences.push(tFn("validationMissingDropbox", modeLabel));
  const items = errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("");
  return `${sentences.map((s) => `<p>${escapeHtml(s)}</p>`).join("")}<ul>${items}</ul>`;
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

  if (state.correggiTarget) {
    const options = state.trackFolderOptions
      .map((folder) => `<option value="${escapeHtml(folder)}">${escapeHtml(folder)}</option>`)
      .join("");
    html += `
      <div class="dialog-backdrop" data-modal="correggi">
        <div class="dialog elev-lg">
          <div class="dialog-title">${escapeHtml(t("mapDialogTitle"))}</div>
          <div class="dialog-body">
            ${escapeHtml(t("mapDialogBodyPrefix"))}"${escapeHtml(state.correggiTarget.track)}"${escapeHtml(t("mapDialogBodySuffix"))}
            <select class="input" id="correggi-select" style="margin-top:12px;">
              <option value="" disabled selected>${escapeHtml(t("mapFolderPlaceholder"))}</option>
              ${options}
            </select>
          </div>
          <div class="dialog-actions">
            <button type="button" class="btn btn-ghost" id="correggi-cancel">${escapeHtml(t("mapFolderCancel"))}</button>
            <button type="button" class="btn btn-primary" id="correggi-confirm">${escapeHtml(t("mapConfirm"))}</button>
          </div>
        </div>
      </div>
    `;
  }

  if (state.deleteTarget) {
    const deleteTitle = state.deleteTarget.all ? t("deleteAllConfirmTitle") : t("deleteConfirmTitle");
    const deleteBody = state.deleteTarget.all
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

  if (state.dropboxOAuth) {
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
  if (state.authErrorMessage) {
    html += `
      <div class="dialog-backdrop" data-modal="auth-error">
        <div class="dialog elev-lg">
          <div class="dialog-title">${ICONS.validation}${escapeHtml(t("authErrorTitle"))}</div>
          <div class="dialog-body">${escapeHtml(state.authErrorMessage)}</div>
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

  const correggiCancel = document.getElementById("correggi-cancel");
  if (correggiCancel) {
    correggiCancel.addEventListener("click", () => {
      state.correggiTarget = null;
      renderModals();
    });
  }

  const correggiConfirm = document.getElementById("correggi-confirm");
  if (correggiConfirm) {
    correggiConfirm.addEventListener("click", async () => {
      const select = document.getElementById("correggi-select");
      const folder = select.value;
      if (!folder) return;
      const track = state.correggiTarget.track;
      await api().map_track(track, folder);
      state.correggiTarget = null;
      renderModals();
      showToast(tFn("mapSavedMessage", track, folder), "success");
      await refreshInstalled();
      renderSetupsView();
      renderSidebar();
    });
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
      const { setupIds, all } = state.deleteTarget;
      state.deleteTarget = null;
      renderModals();
      if (all) {
        await api().delete_setups(setupIds);
      } else {
        await api().delete_setup(setupIds[0]);
      }
      await refreshInstalled();
      renderSetupsView();
      renderSidebar();
      showToast(t(all ? "deletedAllToast" : "deletedToast"), "success");
    });
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
      showToast(t("dropboxOauthSuccessToast"), "success");
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
      state.authErrorMessage = null;
      renderModals();
    });
  }

  const authErrorSettings = document.getElementById("auth-error-settings");
  if (authErrorSettings) {
    authErrorSettings.addEventListener("click", () => {
      state.authErrorMessage = null;
      renderModals();
      state.view = "settings";
      applyActiveView();
    });
  }
}

// ----- global delegated handlers (survive re-renders) --------------------------

document.addEventListener("click", (e) => {
  const link = e.target.closest("[data-open-link]");
  if (link) {
    e.preventDefault();
    api().open_external_link(link.dataset.openLink);
  }
});

window.addEventListener("DOMContentLoaded", init);
