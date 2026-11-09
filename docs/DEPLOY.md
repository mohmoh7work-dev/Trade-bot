# Deploying mohz bot (Windows VPS)

The MetaTrader5 Python package only runs on Windows and talks to one terminal per
process, so production runs on a Windows server. Every broker account gets its own copy
of the MT5 terminal; the supervisor starts one worker process per running account.

Rough sizing: each logged-in terminal uses about 150-300 MB of RAM, so plan on
roughly 25-50 running accounts on a 16 GB VPS. Measure on yours.

## 1. Server

- Windows Server 2022 (or Windows 10/11), always on.
- Python 3.12, Node 22 (only to build the frontend), Git.
- PostgreSQL 16 (on the VPS or managed). Create a database `mohz` and a user.
- A domain pointing at the VPS, and Caddy (or IIS / nginx) for HTTPS.

## 2. MT5 template

1. Install MetaTrader 5 (the generic MetaQuotes build works with most brokers; a broker's
   own build also works) into `C:\mohz\mt5-template`.
2. Start it once with `terminal64.exe /portable`, then **Tools → Options → Expert Advisors →
   Allow algorithmic trading**. Do not log in to any account. Close it.
3. Set `MOHZ_MT5_TEMPLATE_DIR=C:\mohz\mt5-template`. The first start of each account
   copies this folder to `MOHZ_TERMINALS_DIR\<account id>\`; login checks use
   `_probe_1`, `_probe_2`… copies.

If a broker's server is not found by a generic terminal, install that broker's MT5 build
as the template, or open the probe/account copy once and search for the server under
**File → Open an account**.

## 3. Code and settings

```powershell
git clone --recurse-submodules https://github.com/mohmoh7work-dev/Trade-bot C:\mohz\app
cd C:\mohz\app
py -3.12 -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
.venv\Scripts\pip install MetaTrader5
cd frontend; npm ci; npm run build; cd ..
copy .env.example .env      # then edit it
```

In `.env`:
- `MOHZ_BROKER_KEY` from `.venv\Scripts\python -m mohz.keygen` (run in `backend\`).
  **Back it up somewhere safe.** Losing it means every user must retype their broker password.
- `MOHZ_DATABASE_URL=postgresql+psycopg://mohz:PASSWORD@127.0.0.1:5432/mohz`
- `MOHZ_CONNECTOR=mt5`, `MOHZ_MT5_TEMPLATE_DIR`, `MOHZ_COOKIE_SECURE=true`, `MOHZ_TRUST_PROXY=true`
- Restrict the `.env` file and the `data\` folder to the service account (NTFS permissions).

## 4. Services

Run both as Windows services (for example with NSSM), working directory `C:\mohz\app\backend`:

| service | command |
| --- | --- |
| mohz-api | `C:\mohz\app\.venv\Scripts\uvicorn.exe mohz.app:app --host 127.0.0.1 --port 8000` |
| mohz-supervisor | `C:\mohz\app\.venv\Scripts\python.exe -m mohz.supervisor` |

The supervisor must run under a user session that can start MT5 terminals (MT5 needs a
desktop session; use a service account that is logged on, or NSSM's "interact with
desktop" / a scheduled task at logon if the terminals do not start as a pure service).

On a restart the supervisor brings back every bot that was running. Stopping the
supervisor service leaves trades as they are (bots pause, they are not "stopped").

## 5. HTTPS (Caddy)

```
your-domain.com {
    reverse_proxy 127.0.0.1:8000 {
        flush_interval -1        # live updates (Server-Sent Events)
    }
}
```

Only ports 80/443 should be open to the internet. Keep RDP behind a VPN or an IP allowlist.

## 6. Telegram alerts (optional)

1. Create a bot with @BotFather; set `MOHZ_TELEGRAM_BOT_TOKEN` and `MOHZ_TELEGRAM_BOT_USERNAME`.
2. Pick a random `MOHZ_TELEGRAM_WEBHOOK_SECRET`, then register the webhook once:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-domain.com/api/telegram/webhook&secret_token=<SECRET>
```

Users connect from **Account details → Connect Telegram**.

## 7. Updating the engine

The engine is pinned to a commit. To take a new version:

```bash
cd engine-src && git fetch && git checkout <commit> && cd ..
git add engine-src && git commit -m "Engine: update to <commit>"
```

Run the backend tests, then restart the supervisor (running bots come back on the new engine).

## Notes

- Each account's engine data (its own SQLite: council transcripts, orders, trades) is in
  `data\accounts\<id>\engine.db`; the worker's log is `worker.log` next to it.
- The news calendar is downloaded once an hour into `data\calendar.json` and shared.
- The engine's `mt5_offset_hours` (server clock minus New York) is detected at login when
  the market is open; otherwise it stays 7, which suits most brokers.
