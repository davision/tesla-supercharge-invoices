# Tesla Invoicer

Poll the Tesla Fleet API for new charging session invoices, download the PDFs, and upload them to a Dropbox folder. Designed to run on a Synology NAS via **Task Scheduler**.

## What it does

1. Refreshes a Tesla OAuth access token (stored after one-time setup)
2. Calls `GET /api/1/dx/charging/history` for recent charging sessions
3. For each session with an invoice, downloads `GET /api/1/dx/charging/invoice/{contentId}`
4. Uploads the PDF to your configured Dropbox folder
5. Tracks processed invoice IDs in `state.json` so reruns are idempotent

## Prerequisites

### Tesla Developer app

1. Create an app at [developer.tesla.com](https://developer.tesla.com)
2. OAuth grant type: **Authorization Code and Machine-to-Machine**
3. **Allowed Origin URL(s):** `http://localhost:8585`
4. **Allowed Redirect URI(s):** `http://localhost:8585/callback`
5. **Allowed Returned URL(s):** `http://localhost:8585/callback` ← easy to miss; required after the consent screen
6. Enable scope: **Vehicle Charging Management** (`vehicle_charging_cmds`)

All three URL fields must match **exactly** — including `localhost` (not `127.0.0.1`), port `8585`, and the `/callback` path.

**Tip:** Set scopes and all URL fields in the Tesla portal first, save, wait a couple of minutes, then run `setup_auth.py`. Editing the app during an in-progress browser login can cause the post-permission redirect to fail.

### Dropbox app

1. Create an app at [dropbox.com/developers/apps](https://www.dropbox.com/developers/apps)
2. Choose **Scoped access** → **Full Dropbox** or **App folder**
3. Enable permissions: `files.content.write` (and `files.metadata.read` if you use an older token workflow)
4. **Generate a new access token** after saving permissions — tokens created before enabling scopes will not work
5. Paste the token into `DROPBOX_ACCESS_TOKEN` in `.env`

See [Dropbox folder location](#dropbox-folder-location) below — App folder vs Full Dropbox changes where files appear in the UI.

## Setup

```bash
cd tesla-invoicer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python setup_auth.py
python sync_invoices.py
```

Run `setup_auth.py` on any machine with a browser (your laptop is fine). It saves the refresh token to `state.json`. Copy `state.json` to the NAS alongside the script.

## Usage

```bash
# Normal run — download new invoices only
python sync_invoices.py

# Re-download all invoices (ignore previous sync history)
python sync_invoices.py --reset
```

### `--reset` flag

The script tracks which invoices it has already handled in `state.json` (`processed_invoices`). On each run it skips those IDs so reruns are safe and fast.

Use `--reset` when you want to start over, for example:

- You deleted local PDFs from `invoices/` and want them downloaded again
- You changed Dropbox settings and want to re-upload everything
- You are testing after fixing Dropbox or Tesla configuration

`--reset` clears the processed-invoice list only. It does **not** remove your Tesla OAuth tokens — you do not need to run `setup_auth.py` again.

## Dropbox folder location

This is a common source of confusion.

The log prints paths like `Uploaded to Dropbox: /invoices/4037P123257.pdf`. Where that file appears in the Dropbox UI depends on your **app type**:

| App type | What `DROPBOX_FOLDER=/invoices` means | Where to look in Dropbox |
|---|---|---|
| **App folder** | A folder inside the app's sandbox | **Apps → your-app-name → invoices** |
| **Full Dropbox** | A folder at the root of your account | **invoices** (top level) or any path you configure |

With an **App folder** app, paths are relative to `Dropbox/Apps/<app-name>/`, not your main Dropbox tree. So `/Podjetje/Podjetje 2026/Prejeti` does **not** upload to your real business folder — it creates that path **inside** the app sandbox.

To upload directly to a folder like `/Podjetje/Podjetje 2026/Prejeti` in your main Dropbox:

1. Create a **Full Dropbox** app (not App folder)
2. Generate a new access token
3. Set `DROPBOX_FOLDER=/Podjetje/Podjetje 2026/Prejeti` in `.env`
4. Run `python sync_invoices.py --reset`

## Synology Task Scheduler

1. Install **Python 3** from Package Center (or use an existing install)
2. Copy the project to the NAS, e.g. `/volume1/scripts/tesla-invoicer/`
3. Install dependencies into a venv on the NAS
4. Place `.env` and `state.json` in that folder
5. Create a **Scheduled Task** → **User-defined script**:

```bash
/volume1/scripts/tesla-invoicer/.venv/bin/python /volume1/scripts/tesla-invoicer/sync_invoices.py --env-file /volume1/scripts/tesla-invoicer/.env
```

A daily or hourly schedule is usually enough. Charging invoices typically appear shortly after a session ends.

## Configuration

| Variable | Description |
|---|---|
| `TESLA_CLIENT_ID` | Tesla app client ID |
| `TESLA_CLIENT_SECRET` | Tesla app client secret |
| `TESLA_REGION` | `na` or `eu` (match your Tesla account region) |
| `TESLA_VIN` | Optional — limit to one vehicle |
| `INVOICES_DIR` | Local folder for PDFs (default: `./invoices`) |
| `DROPBOX_ACCESS_TOKEN` | Optional Dropbox API token (omit to save locally only) |
| `DROPBOX_FOLDER` | Dropbox destination path (see [Dropbox folder location](#dropbox-folder-location)) |
| `STATE_FILE` | Path to token/state JSON (default: `./state.json`) |
| `LOG_FILE` | Optional log file path |

## Files

| File | Purpose |
|---|---|
| `setup_auth.py` | One-time OAuth login, saves refresh token |
| `sync_invoices.py` | Main job for Task Scheduler (`--reset` to re-sync all invoices) |
| `state.json` | OAuth tokens + processed invoice IDs (created at runtime, chmod 600) |

## Notes

- Invoices use Tesla's `contentId` as the deduplication key.
- If token refresh fails, rerun `setup_auth.py`.
- The `charging/sessions` endpoint is for Tesla for Business fleet accounts only; this script uses `charging/history`, which works for personal accounts with the charging scope.
