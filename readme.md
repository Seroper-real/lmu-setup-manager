# LMU Setup Manager

🇮🇹 [Leggi questo README in Italiano](readme.it.md)

<p align="center">
  <a href="https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip">
    <img src="https://img.shields.io/github/v/release/Seroper-real/lmu-setup-manager?label=DOWNLOAD&style=for-the-badge&color=brightgreen" alt="Download">
  </a>
  <a href="https://ko-fi.com/seroper">
    <img src="https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support me on Ko-fi">
  </a>
</p>

A desktop **setup manager** for *Le Mans Ultimate*. It installs car setups into the game, keeps a catalogue of what you have, replaces them when a newer version comes out and lets you clean them up again — all from one window.

Setups get in two ways:

- **Automatically from TrackTitan** — your whole subscription in a single run, instead of grabbing setups one by one from the website.
- **Manually** — drop in any `.zip` you already have (GO Setups archives, a friend's setup, your own) and tell the app which car and track it's for.

Either way they end up managed the same: listed, updated, and removable from the app. No files to create or edit by hand.

<details>
<summary><b>Before you start — what this tool is and isn't</b></summary>

- It **does not bypass paywalls or limitations**. The TrackTitan integration needs a **valid TrackTitan account with an active subscription** — without one that part simply won't work, though you can still use the app to manage setups you add by hand.
- Data is retrieved using the **same APIs the official TrackTitan web app uses**.
- This project is **not affiliated with, supported by, or endorsed by TrackTitan**, and is intended **for personal use only**.

</details>

---

## Requirements

- A Windows PC
- Le Mans Ultimate installed
- A TrackTitan account with an active LMU setups subscription

---

## Step 1 — Install

1. [Download](https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip) the `.zip`
2. Extract it wherever you like
3. Run the `.exe` inside

There's no installer and nothing is written into the program folder — you can move or delete it later without losing your setups or settings.

> The app starts in Italian. Switch to English from **Settings → Language**.

---

## Step 2 — Pick your mode

Open **Settings → Operating mode** and choose one. The choice takes effect immediately, no restart needed.

| Mode | In the app | What it does | You'll need |
| :--- | :--- | :--- | :--- |
| `full` *(default)* | **Direct** | Downloads from TrackTitan and installs straight into LMU on this PC | TrackTitan login + LMU folder |
| `master` | **Upload only** | Downloads from TrackTitan and publishes to your own Dropbox (no local install) | TrackTitan login + Dropbox app |
| `slave` | **Install only** | Pulls setups from your own Dropbox and installs them into LMU on this PC | Dropbox app (read-only is enough) + LMU folder |

**On a single PC, use Direct.** The other two only make sense if you run Le Mans Ultimate on **more than one of your own PCs** and want to move setups between them through your own Dropbox — see [Modes in detail](#modes-in-detail).

---

## Step 3 — First run, by mode

### Direct — the normal case

1. **Settings → TrackTitan tokens → Get automatically.** A TrackTitan login window opens inside the app. Sign in as you normally would; the window closes on its own and your three tokens are filled in and saved.
2. **Settings → Le Mans Ultimate setup folder.** Check the path. If the game isn't in the default Steam location, hit **Browse…** and point it at:
   `…\Le Mans Ultimate\UserData\player\Settings`
3. Go to the **Download** tab and press **Start download**.

> On the very first run the app warns you that HYMO setups you installed *before* using this tool are invisible to it. It's recommended to delete those old HYMO setups from LMU first, so this app can manage everything cleanly from here on.

### Upload only — the PC that has your subscription

1. Create a Dropbox app once — see [Creating your Dropbox app](#creating-your-dropbox-app) (about 3 minutes, no coding).
2. **Settings → TrackTitan tokens → Get automatically**, same as Direct above.
3. **Settings → Dropbox credentials.** Paste `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET`, then click **Get automatically** next to the refresh token and choose **Read/Write Token**. Approve the app on the Dropbox page that opens, paste the short code back into the app, and it's saved.
4. Check the **shared Dropbox folder** field (default `/lmu-setups`) — it has to match on your other PC.
5. **Download** tab → **Start download**.

No LMU path is needed here — nothing is installed locally.

### Install only — your other PC(s)

**No TrackTitan subscription or tokens are needed on this machine.**

1. **Settings → Dropbox credentials.** Paste the same `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET` as the other PC, click **Get automatically** and choose **Read Only Token** — that credential can never write to or delete anything in your Dropbox.
2. Set the **shared Dropbox folder** to the same value you used in Upload only.
3. **Settings → Le Mans Ultimate setup folder** — check the path, **Browse…** if needed.
4. **Download** tab → **Start download**.

---

## The app, tab by tab

**Download** — Shows the active mode, a **Start download** / **Stop** button and a live activity feed of everything that gets installed or uploaded as it happens. Only new and updated setups are fetched, so a second run right after the first has almost nothing to do.

**Installed setups** — Everything this app has installed, grouped by track and car, with the car's class logo and a **Hotlap** link that opens TrackTitan's YouTube lap for that setup. Search by track or car, and delete a single setup, a whole car, everything for one track, or everything at once.

**Upload Setup** — Drag in a `.zip` (or click to browse), pick the type (**GO Setups** or **HYMO**), the track and the car, and press **Upload setup**. In Direct/Install only it's installed straight into LMU; in Upload only it's published to your Dropbox for your other PCs. The track and car are pre-guessed from the filename when possible. This is the easy way to add [GO Setups](#go-setups) archives.

**Manual associations** — The track and car names you've mapped by hand (see [When a setup isn't recognized](#when-a-setup-isnt-recognized)). Searchable, paginated, and you can delete a single mapping or all of them.

**Settings** — Language, operating mode, LMU folder, TrackTitan tokens, Dropbox credentials, plus a collapsed **Advanced settings** block (every field has an ⓘ tooltip explaining it) and a [Danger zone](#danger-zone).

> There's no Save button in Settings — the app asks whether to save when you leave the tab or close the window.

---

## Things you'll run into

### When a setup isn't recognized

A setup is only installed once the app can tell **which track and which car** it's for. If either can't be matched, that setup is skipped — nothing lands in a wrongly-named folder.

At the end of a run, the app collects everything it skipped and opens a **Unrecognized setups** dialog listing each unknown track or car once. For each one, pick the correct track/car from the dropdown, then press **Save and Rerun** to immediately process them, or **Save and Close** to fix it on the next run. Your choices are stored locally and reused forever after — they show up in the **Manual associations** tab.

If the right track or car isn't in the dropdown either, use **Copy list** and open an issue: the built-in mapping needs updating, which is done on our side without you having to update the app.

### Tokens expiring

TrackTitan tokens expire regularly. When they do, the app tells you with an **Authentication expired** popup — just hit **Get automatically** again in Settings and re-run.

Dropbox credentials don't expire: the refresh token is generated once and renews itself.

### Setups being updated

When TrackTitan publishes a new version of a setup you already have, the app notices and replaces it — in LMU, and on Dropbox for Upload only. You don't have to track versions yourself.

---

## Support my work

If you find this project useful and want to support its development, consider buying me a coffee! Every coffee helps me keep the lights on and the code flowing.

[![](https://storage.ko-fi.com/cdn/kofi3.png?v=3)](https://ko-fi.com/seroper)

---
---

# Advanced / Reference

Everything below is background material — you don't need any of it to use the app.

## Modes in detail

By default the tool runs in **Direct** mode (`full`) and does everything on one machine: download from TrackTitan, install into LMU, remember what's installed in a local database.

If you run Le Mans Ultimate on **more than one of your own PCs**, the other two modes let you move setups through **your own Dropbox** instead of extracting tokens and hammering TrackTitan from every machine:

- **Upload only** (`master`) — runs on the PC with your TrackTitan subscription. It downloads your setups, repackages them, and mirrors them into your Dropbox under `<Dropbox folder>/<Car>/<Track>/HYMO-<track>_<car>_<id>_<timestamp>.zip`. It keeps no local database: it works out what to publish by comparing TrackTitan against what's already in the folder. When a setup is updated, the new zip is uploaded first and only then the old one is deleted.
- **Install only** (`slave`) — runs on your other PCs. It lists that same folder, skips whatever the local database already has at the same version or newer, downloads the rest and installs it. It rebuilds each setup's details from a `.metadata.json` embedded in the zip, so an Install only machine ends up with exactly the same records a Direct one would.

Only the TrackTitan side is rate-limited (roughly one setup every couple of seconds, so a first full run takes on the order of 20–30 minutes). Uploads to Dropbox run in parallel in the background and don't add to that time.

## Creating your Dropbox app

Needed for Upload only and Install only. About three minutes, once.

### 1. Create the app

Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps) and click **Create app**:

- Choose **Scoped access**
- Choose **App folder** — this limits the app to `/Apps/<YourAppName>/` instead of your whole Dropbox
- Give it a unique name

The **Settings** tab of your new Dropbox app now shows an **App key** and an **App secret** — these are `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET`.

> With **App folder** access, the Dropbox folder you set in the app is relative to the app folder: `/lmu-setups` physically lives at `/Apps/<YourAppName>/lmu-setups`. Keep writing `/lmu-setups`.

### 2. Enable the permissions

Open the **Permissions** tab and tick:

| Scope | Needed by |
| :--- | :--- |
| `files.metadata.read` | Upload only + Install only (listing the folder) |
| `files.content.read` | Install only (downloading setups) |
| `files.content.write` | Upload only (uploading and replacing setups) |

Press **Submit** at the bottom, otherwise nothing is saved.

### 3. Get the refresh token

Use **Get automatically** in the app's Settings, as described in [Step 3](#upload-only--the-pc-that-has-your-subscription). Pick **Read/Write** on the Upload only PC and **Read Only** on the Install only ones — a read-only refresh token can never be widened later, so that machine physically cannot damage your folder.

<details>
<summary>Generating the refresh token by hand</summary>

Open this URL in your browser, replacing `<REPLACE_WITH_APP_KEY>` with your own:

```
https://www.dropbox.com/oauth2/authorize?client_id=<REPLACE_WITH_APP_KEY>&token_access_type=offline&response_type=code
```

For a read-only credential, append `&scope=files.metadata.read%20files.content.read` to that URL.

Authorize the app. Dropbox shows a short **access code** — this is *not* the refresh token; it's single-use and expires within minutes. Exchange it without leaving the page:

1. Stay on the Dropbox page showing the code.
2. Open the developer tools (`F12`) and select the **Console** tab.
3. Paste the snippet below, replacing the three placeholders, and press Enter.

```js
(async () => {
  const APP_KEY    = 'PASTE_APP_KEY';
  const APP_SECRET = 'PASTE_APP_SECRET';
  const CODE       = 'PASTE_CODE_FROM_THIS_PAGE';

  const res = await fetch('https://api.dropbox.com/oauth2/token', {
    method: 'POST',
    headers: { Authorization: 'Basic ' + btoa(`${APP_KEY}:${APP_SECRET}`) },
    body: new URLSearchParams({ code: CODE, grant_type: 'authorization_code' }),
  });
  const data = await res.json();
  if (!data.refresh_token) return console.error('Dropbox returned an error:', data);
  console.log(`DROPBOX_APP_KEY=${APP_KEY}\nDROPBOX_APP_SECRET=${APP_SECRET}\nDROPBOX_REFRESH_TOKEN=${data.refresh_token}`);
})();
```

The console prints the three values, ready to paste into the app's Settings tab.

**Troubleshooting**

- The first time you paste into the Chrome/Edge console it refuses and asks you to type `allow pasting` and press Enter. Do that once, then paste again.
- Dropbox's own page code wraps `console.log` and appends a collapsed `Error` entry (it captures a stack trace for their logging). It's harmless — ignore it.
- If you see `invalid_grant`, the code was already used or has expired: reload the authorization URL to get a fresh one.
- Do **not** paste the `access_token` from the response: access tokens start with `sl.` and stop working after a few hours. You want `refresh_token`.

Prefer the terminal?

```bash
curl -u APP_KEY:APP_SECRET \
  -d code=YOUR_CODE \
  -d grant_type=authorization_code \
  https://api.dropbox.com/oauth2/token
```

</details>

## Extracting TrackTitan tokens by hand

Only needed if **Get automatically** fails for you.

1. Log in to https://app.tracktitan.io in your browser.
2. Open the developer tools (`F12`, or `Cmd + Option + I` on macOS) and go to the **Console** tab.
3. Paste this single line and press Enter:

```
(()=>{let a,b,u;document.cookie.split(';').forEach(c=>{const[k,v]=c.trim().split(/=(.*)/s);/\.accessToken$/.test(k)&&(a=v);/\.idToken$/.test(k)&&(b=v);/\.LastAuthUser$/.test(k)&&(u=v);});console.log(`ACCESS_TOKEN_LIST=${a}\nACCESS_TOKEN_DOWNLOAD=${b}\nUSER_ID=${u}`);})();
```

4. It prints something like:

```
ACCESS_TOKEN_LIST=eyJraWQiOiIzNDd2Q3lpWllCRWdJSkw3...
ACCESS_TOKEN_DOWNLOAD=eyJraWQiOiI3MEoyS3lmVHZQXC9ocUJ0...
USER_ID=123cdvf-34fd...
```

5. Paste each value into the matching field in **Settings → TrackTitan tokens**.

> Tokens and Dropbox credentials are sensitive — **never share them**.

## GO Setups

The setups this tool manages end to end come from TrackTitan and are published under the **HYMO** brand. **GO Setups** is a separate third-party provider that is only *compatible* with this tool: the app never talks to GO's systems and doesn't publish anything on GO's behalf. You supply the archives yourself.

**Adding one:** use the **Upload Setup** tab — drop the zip, choose type **GO Setups**, pick track and car, confirm. In Direct/Install only it's installed locally; in Upload only it's published to Dropbox for your other PCs to pick up. Uploading again for the same car and track replaces the previous archive.

Details:

- GO archives live on the same Dropbox tree as HYMO ones, at `<Dropbox folder>/<Car>/<Track>/`, with a `GO-` filename prefix. Dropping a zip into that folder manually works too, as long as the name starts with `GO`.
- A GO archive's MoTeC telemetry files (`.ld`/`.ldx`) are installed alongside its `.svm` setups on purpose — GO ships them together, so they're copied in and cleaned up together.
- GO gives no reliable "this changed" signal, so every Install only run re-downloads every GO archive it finds. That's expected. Whether it's actually reinstalled depends on content only: the app fingerprints the download and skips the reinstall when nothing changed. This also means an archive can be renamed in place without losing its install history — only moving it to a different `<Car>/<Track>` folder starts a fresh, unrelated one.
- GO setups appear in the **Installed setups** tab like any other, with a small **GO** badge next to them.

## Track and car mapping

TrackTitan's raw track and car names are matched against a mapping bundled with the app (`config/mapping.json`) using case-insensitive pattern matching. That file is refreshed automatically from GitHub at startup, so new tracks and cars can be added without you updating the app — you can turn that off under **Advanced settings → Remote tracks**.

Anything the bundled mapping doesn't recognize falls through to your own **Manual associations**, added via the end-of-run dialog described [above](#when-a-setup-isnt-recognized). If neither layer matches, the setup is skipped rather than installed under a made-up name.

The car mapping also carries each car's class, which is what draws the GT3/GTE/Hypercar/P2/P3 logos in the **Installed setups** tab.

## Where your data lives

| What | Where |
| :--- | :--- |
| Settings, credentials, manual associations (`settings.db`) | `%LOCALAPPDATA%\lmu-setup-manager` |
| Record of installed setups (`data.db`) | `%LOCALAPPDATA%\lmu-setup-manager` |
| Log files | `logs\` next to the `.exe` (one per day, old ones pruned automatically) |
| Temporary downloads | `downloads\` next to the `.exe` |

Because settings and the installed-setups database live in your user data folder, they **survive reinstalls and version upgrades** — you can safely delete or move the extracted program folder.

Deleting the installed-setups database means **starting all downloads from scratch**: the app no longer knows what it already installed.

## Advanced settings

Under **Settings → Advanced settings** (collapsed by default). Every field has an ⓘ tooltip in the app; the defaults are sane and you rarely need to touch these.

| Group | What's in it |
| :--- | :--- |
| Logging | Minimum level written to the log file |
| Network | TrackTitan page size, request timeout, and the min/max delay between requests |
| Download and setup | Which file extensions count as setups, whether to clean the download folder, whether to overwrite existing setups and whether to delete the previous version |
| Remote tracks | Automatic track/car mapping updates: on/off, source URL, timeout |
| Dropbox (advanced) | API timeout and how many uploads run in parallel |

## Danger zone

At the bottom of **Settings**, behind a confirmation with a countdown:

- **Clean Dropbox setups** — deletes every setup in your shared Dropbox folder. Nothing local is touched.
- **Restore factory settings** — deletes every setup this app installed plus all app data (settings, credentials, database). Your Dropbox is left alone.

Both are irreversible.

## Sandbox (for contributors)

For developing and testing the tool itself. Each flag swaps one external system for a local stand-in, so you can run the app on a machine with no TrackTitan subscription and no copy of Le Mans Ultimate. They're command-line flags — nothing is written to your real settings/credentials — and combine freely.

```
python src/main.py --sandbox                     # mock everything
python src/main.py --mock-tracktitan --mock-lmu  # mock these two, use real Dropbox
python src/main.py --sandbox --mode master       # sandbox, forcing a mode
```

| Flag | Effect |
| :--- | :--- |
| `--sandbox` | Shortcut for all three `--mock-*` flags below |
| `--mock-tracktitan` | Serve setups from the sample catalog in `sandbox/tracktitan/` instead of calling the TrackTitan API. No tokens needed |
| `--mock-lmu` | Install into `sandbox/lmu/Settings/` instead of the game folder. Uses a separate database, so your real installation records are untouched |
| `--mock-dropbox` | Use the local `sandbox/dropbox/` folder instead of Dropbox. No credentials needed |
| `--mock-base-path PATH` | Where the sandbox lives. Defaults to `sandbox` |
| `--mode {full,master,slave}` | Override the stored mode for this run only |

Each flag also drops the matching credential requirement, so `--sandbox --mode master` then `--sandbox --mode slave` runs a full publish → install round trip with no credentials configured at all. Every sandbox run logs a `SANDBOX ACTIVE` warning so you can never mistake it for a real one. The equivalent `MOCK_TRACKTITAN` / `MOCK_LMU` / `MOCK_DROPBOX` / `MODE` environment variables work too, and `.vscode/launch.json` ships a debug profile for each combination.

`sandbox/dropbox/` already ships one GO Setups fixture per track (synthetic `.svm`/`.ld`/`.ldx` placeholders, not real setup data), so `--mock-lmu --mock-dropbox --mode slave` installs all of them immediately. To exercise the update path by hand, run it twice: the second run should log "unchanged since last install" and touch nothing; edit a fixture member's content and rerun to see the version-bump path reinstall and clean up the old files.

## Running and building from source

```bash
pip install -r requirements.txt
python src/main.py
```

`build.bat` produces the standalone Windows `.exe` in `dist/` via PyInstaller. Releases are built automatically by GitHub Actions when a `v*` tag is pushed.
