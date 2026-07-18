# LMU Setup Manager for Le Mans Ultimate

🇮🇹 [Leggi questo README in Italiano](readme.it.md)

<p align="center">
  <a href="https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip">
    <img src="https://img.shields.io/github/v/release/Seroper-real/lmu-setup-manager?label=DOWNLOAD&style=for-the-badge&color=brightgreen" alt="Download">
  </a>
</p>

## Introduction

This project was created **purely for convenience**.

Its goal is to automate the download and installation of **TrackTitan** setups for *Le Mans Ultimate*, avoiding the need to manually download each setup from the website. Everything is driven from a graphical app — no files to create or edit by hand.

⚠️ **Important notice**

- This tool **does not bypass paywalls or limitations**
- A **valid TrackTitan account with an active subscription** is required
- Data is retrieved using the **same APIs used by the official TrackTitan web app**
- Authentication tokens must be **manually obtained via browser**

This project:

- Is **not affiliated with TrackTitan**
- Is **not supported or endorsed by TrackTitan**
- Is intended **for personal use only**

Without an active subscription, this tool **will not work**.

---

## Requirements

- A valid TrackTitan account with an active LMU setups subscription
- Windows PC
- Le Mans Ultimate installed

---

## Quick Start

### 1. Download and extract

1. [Download](https://github.com/Seroper-real/lmu-setup-manager/releases/latest/download/lmu-setup-manager_Windows.zip) the `.zip` file
2. Extract the contents to a folder of your choice
3. Run the `.exe` inside

### 2. Pick your mode

Open the **Settings** tab (or the mode picker on the Download tab) and choose:

| Mode              | What it does                                                               | You'll need                                |
| :---------------- | :-------------------------------------------------------------------------- | :------------------------------------------- |
| `full` (default) | Download from TrackTitan and install straight into LMU on this PC          | TrackTitan tokens + LMU path               |
| `master`         | Download from TrackTitan and push into your own Dropbox (no local install) | TrackTitan tokens + Dropbox credentials    |
| `slave`          | Pull setups from your own Dropbox and install into LMU on this PC          | Dropbox credentials (read-only) + LMU path |

The choice takes effect immediately, no restart needed. `master`/`slave` are only useful if you run LMU on more than one of your own PCs — see [Modes in detail](#modes-in-detail) below. On a single PC, stick with `full`.

### 3. Enter your credentials

Still in the **Settings** tab, paste your tokens into the matching fields:

- **TrackTitan tokens** (`full`/`master`) — see the [dedicated guide](#tracktitan-tokens) below
- **Dropbox credentials** (`master`/`slave`) — see the [dedicated guide](#dropbox-credentials) below

Each field in Settings also has a "Look here" link that jumps straight to the relevant guide.

### 4. Set the LMU install path

Needed for `full`/`slave`. Check the LMU path field in Settings — use the **Browse** button if it's wrong or the game isn't at the default location.

### 5. Run it

Hit **Start** on the Download tab 🚀

---

<a id="tracktitan-tokens"></a>

## 🔑 Getting your TrackTitan tokens

Needed for `full` and `master` modes.

**Recommended: from the app**

1. Open the Settings tab and click **Get automatically** next to the TrackTitan token fields — this opens a TrackTitan login window inside the app.
2. Log in normally in that window, exactly as you would in a browser.
3. Once you're signed in, the window closes on its own and `ACCESS_TOKEN_LIST`, `ACCESS_TOKEN_DOWNLOAD` and `USER_ID` are filled in for you.
4. Click **Save** and you're done, no need for the manual method below.

<details>
<summary>Alternative: extract them manually</summary>

1. Log in to https://app.tracktitan.io in your own browser.
2. Open the browser developer tools
   - Windows/Linux: `F12` or `Ctrl + Shift + I`
   - macOS: `Cmd + Option + I`
3. Open the **Console** tab and paste this single line, then press Enter:

```
(()=>{let a,b,u;document.cookie.split(';').forEach(c=>{const[k,v]=c.trim().split(/=(.*)/s);/\.accessToken$/.test(k)&&(a=v);/\.idToken$/.test(k)&&(b=v);/\.LastAuthUser$/.test(k)&&(u=v);});console.log(`ACCESS_TOKEN_LIST=${a}\nACCESS_TOKEN_DOWNLOAD=${b}\nUSER_ID=${u}`);})();
```

4. The console prints something like:

```
ACCESS_TOKEN_LIST=eyJraWQiOiIzNDd2Q3lpWllCRWdJSkw3...
ACCESS_TOKEN_DOWNLOAD=eyJraWQiOiI3MEoyS3lmVHZQXC9ocUJ0...
USER_ID=123cdvf-34fd...
```

5. Paste each value into the matching TrackTitan field in the app's Settings tab and click **Save**.

</details>

> ⚠️ Tokens **expire**. If you get a `401 Unauthorized` popup, just repeat the steps above and save again.

---

<a id="dropbox-credentials"></a>

## 📦 Creating your Dropbox app & tokens

Needed for `master` and `slave` modes. Takes about five minutes and only needs to be done once (the refresh token doesn't expire).

### 1. Create the app

Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps) and click **Create app**:

- Choose **Scoped access**
- Choose **App folder** — this limits the app to `/Apps/<YourAppName>/` instead of your whole Dropbox
- Give the app a unique name

The **Settings** tab of your new Dropbox app now shows an **App key** and **App secret** — these are `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET`.

> With **App folder** access, the Dropbox folder path you set in the app's Settings is relative to the app folder: `/lmu-setups` physically lives at `/Apps/<YourAppName>/lmu-setups`. Keep using `/lmu-setups`.

### 2. Enable the permissions

Open the **Permissions** tab and tick:

| Scope                  | Needed by                                |
| :---------------------- | :---------------------------------------- |
| `files.metadata.read` | MASTER + SLAVE (listing the folder)      |
| `files.content.read`  | SLAVE (downloading setups)               |
| `files.content.write` | MASTER (uploading and replacing setups)  |

Press **Submit** at the bottom of the page, otherwise the changes are not saved.

### 3. Generate the refresh token

**Recommended: from the app**

1. Paste `DROPBOX_APP_KEY` and `DROPBOX_APP_SECRET` into the matching fields in the app's Settings tab.
2. Click **Get automatically** next to the Refresh Token field — this opens the Dropbox authorization page in your browser.
3. Approve the app. Dropbox shows a short **access code**.
4. Back in the app, paste that code into the dialog that just appeared and click **Confirm**.

The app exchanges the code for you and fills in `DROPBOX_REFRESH_TOKEN` automatically — click **Save** and you're done, no need for the manual method below.

<details>
<summary>Alternative: generate it manually</summary>

Open this URL in your browser, replacing `<REPLACE_WITH_APP_KEY>` with your own:

```
https://www.dropbox.com/oauth2/authorize?client_id=<REPLACE_WITH_APP_KEY>&token_access_type=offline&response_type=code
```

Authorize the app. Dropbox then shows a short **access code** — this is *not* the refresh token, it's single-use and expires within minutes. Exchange it without leaving the page:

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

The console prints the three values, ready to paste into the app's Settings tab:

```
DROPBOX_APP_KEY=abc123...
DROPBOX_APP_SECRET=def456...
DROPBOX_REFRESH_TOKEN=8vTq...
```

<details>
<summary>Troubleshooting the console step, and a curl alternative</summary>

- The first time you paste into the Chrome/Edge console it refuses and asks you to type `allow pasting` and press Enter. Do that once, then paste again.
- Dropbox's own page code wraps `console.log` and appends a collapsed `Error` entry (it captures a stack trace for their logging). It shows up right under the output and is harmless — ignore it.
- If the console shows `invalid_grant`, the code was already used or has expired: reload the authorization URL to get a fresh code, then run the snippet again.

Prefer the terminal? Use curl instead:

```bash
curl -u APP_KEY:APP_SECRET \
  -d code=YOUR_CODE \
  -d grant_type=authorization_code \
  https://api.dropbox.com/oauth2/token
```

In the JSON response, the `refresh_token` field is your `DROPBOX_REFRESH_TOKEN`. Do **not** paste the `access_token` from the same response: access tokens start with `sl.` and stop working after a few hours.

</details>

</details>

### 4. Read-only token for the SLAVE PC (optional)

If you're setting up a second PC in `slave` mode, don't reuse the MASTER token there — generate a second, read-only one instead. The **Get automatically** button in the app always requests full access, so this one has to be done manually: repeat the steps above with a reduced `scope` parameter in the authorization URL:

```
https://www.dropbox.com/oauth2/authorize?client_id=<REPLACE_WITH_APP_KEY>&token_access_type=offline&response_type=code&scope=files.metadata.read%20files.content.read
```

The resulting refresh token carries only those two scopes, and scopes can never be widened later — so this credential can never write to your folder. Use the full-scope token on MASTER and this read-only one on SLAVE.

### 5. Enter the credentials in the app

Paste the three values into the matching Dropbox fields in the app's Settings tab:

```
DROPBOX_APP_KEY=...
DROPBOX_APP_SECRET=...
DROPBOX_REFRESH_TOKEN=...
```

Finally, set the Dropbox folder in Settings (default `/lmu-setups`) — it must be the same on MASTER and SLAVE. Click **Save**.

> Keep these credentials private, exactly like the TrackTitan tokens.

---

## Important Notes

- Tokens **expire**: if you receive `401 Unauthorized` errors (a popup will tell you), repeat the token steps and re-save them in Settings
- **Never share** your credentials
- Downloads are delayed slightly to simulate human behavior (about one setup every ~2 seconds, total time ~20–30 minutes)
- Already installed setups, and all of your settings/credentials, are stored in your OS's per-user app data folder (e.g. `%LOCALAPPDATA%\lmu-setup-manager` on Windows) — it survives reinstalls and version upgrades, so it's safe to delete or move the extracted program folder
- Deleting the installed-setups database means **starting downloads from the beginning**
- To stop a run, use the **Stop** button on the Download tab (or just close the app window)

---

## ☕ Support my work

If you find this project useful and want to support its development, consider buying me a coffee!

[![](https://storage.ko-fi.com/cdn/kofi3.png?v=3)](https://ko-fi.com/seroper)

*Every coffee helps me keep the lights on and the code flowing.*

---

## Advanced / Reference

Everything below is background material — you don't need it to get the tool running. The app's Settings tab has an ⓘ tooltip on every advanced field, so this section sticks to concepts rather than duplicating field-by-field documentation.

### Modes in detail

By default the tool runs in **FULL** mode and does everything on one machine: download from TrackTitan and install into LMU.

If you run Le Mans Ultimate on **more than one of your own PCs**, you can move your setups through **your own Dropbox** instead of extracting tokens and querying TrackTitan on every machine. Two extra modes make this possible:

- **MASTER** — run on the PC that has your TrackTitan tokens. It downloads your setups and mirrors them into a folder in **your** Dropbox (one zip per setup, named `{track}_{car}_{id}_{timestamp}.zip`). When a setup is updated, the old copy is replaced automatically.
- **SLAVE** — run on your other PC. It installs the setups straight from your Dropbox folder into LMU. **No TrackTitan tokens are needed here** — only read access to your own Dropbox folder.

### Track mapping

TrackTitan track names are automatically matched to LMU folders using a mapping that's bundled with the app and kept up to date on its own — no action needed on your part.

If a downloaded setup refers to a track that matches nothing, the tool creates a folder named `<TRACK_NAME> - HYMO`, so unmapped tracks are easy to spot. Fix one anytime with the **Correggi** ("Fix") action next to it in the Setup installati tab — pick the right LMU folder from the list. The fix is saved locally and applies immediately, no file to edit.

### Sandbox (for contributors)

For developing and testing the tool itself. Each flag swaps one external system for a local stand-in, so you can run the app on a machine with no TrackTitan subscription and no copy of Le Mans Ultimate installed. They are command-line flags — nothing is written to your real settings/credentials — and combine freely.

```
python src/main.py --sandbox                    # mock everything
python src/main.py --mock-tracktitan --mock-lmu  # mock these two, use real Dropbox
python src/main.py --sandbox --mode master       # sandbox, forcing a mode
```

| Flag                          | Effect                                                                                                                                     |
| :----------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------- |
| `--sandbox`                   | Shortcut for all three `--mock-*` flags below.                                                                                              |
| `--mock-tracktitan`           | Serve setups from the sample catalog in `sandbox/tracktitan/` instead of calling the TrackTitan API. No tokens needed.                      |
| `--mock-lmu`                  | Install into `sandbox/lmu/Settings/` instead of the game folder. Uses a separate database, so your real installation records are untouched. |
| `--mock-dropbox`              | Use the local `sandbox/dropbox/` folder instead of Dropbox. No credentials needed.                                                          |
| `--mock-base-path PATH`       | Where the sandbox lives. Defaults to `sandbox`.                                                                                             |
| `--mode {full,master,slave}` | Override the stored mode for this run only.                                                                                     |

Each flag also drops the matching credential requirement, so `--sandbox --mode master` then `--sandbox --mode slave` runs a full publish → install round trip with no credentials configured at all. Every sandbox run logs a `SANDBOX ACTIVE` warning so you can never mistake it for a real one. The equivalent `MOCK_TRACKTITAN` / `MOCK_LMU` / `MOCK_DROPBOX` / `MODE` environment variables work too, and `.vscode/launch.json` ships a debug profile for each combination.
