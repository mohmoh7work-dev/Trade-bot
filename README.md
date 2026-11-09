# mohz bot

A web dashboard where users connect their MetaTrader 5 accounts and start or stop the
XAUUSD council bot (11 agents) on them. Installable on phones as a PWA.

The bot itself is **not** in this repo: it is the engine from
[mohmoh7work-dev/Trade](https://github.com/mohmoh7work-dev/Trade), pinned as the
`engine-src/` submodule and used unchanged. This repo wraps it.

## How it fits together

```
browser (React PWA) ──HTTPS──> API (FastAPI) ──> database (Postgres / SQLite)
                                                    ▲            ▲
                         supervisor ── reads "wanted" state, writes "actual" state
                              │ starts one process per account
                              ▼
                  worker <account> = the unchanged engine + one MT5 terminal
```

- **Start/Stop** only write `bot_state.desired` to the database. The **supervisor**
  (`python -m mohz.supervisor`) makes reality match: it starts a worker, sends it "stop",
  kills it if it hangs, retries crashes with backoff (5 s, 15 s, 30 s … 10 min), and on
  restart brings back every bot that was running.
- A **worker** (`backend/mohz/worker.py`) builds the engine the same way
  `python -m engine serve --broker mt5` does, with that account's login, symbol, mode and
  settings, and runs the engine's own Runner. Every 5 s it writes a heartbeat, balance,
  equity, today's P/L, open positions and the engine's events (decisions, signals, orders,
  trades, errors) to the database.
- **One worker per broker account, never two:** a server+login can be added once, the
  supervisor keeps one process per account, and each worker holds a lock file.
- **Alerts only** runs the engine in its `alerts` mode (it never calls `execute`), and the
  broker's `place()` is also wrapped to refuse orders. Signals go to the user's Telegram.
- **Auto-stops:** daily loss limit and max drawdown close the bot's trades and stop it
  (the engine's kill switch). The engine's own hard limits (`engine/settings.py`) still apply.
- **Stop bot** closes the bot's open trades by default (per-account setting).
- **Real money:** demo only, unless the user turns on *Allow real money* for that account,
  which needs their password and typing `LIVE`.

## Security

- Broker passwords: AES-256-GCM (`backend/mohz/crypto.py`), key in `MOHZ_BROKER_KEY`,
  each ciphertext bound to its user and account. Never sent back to the browser; the card
  shows dots and editing means typing a new one. Workers get the password on stdin, not
  in arguments or environment, and never get the key.
- User passwords: argon2id. Sessions: httpOnly, Secure, SameSite cookie, stored hashed.
  CSRF token on every write. Login limited to 5 failures per email / 20 per IP per 15 min.
- Every account route checks the account belongs to the logged-in user (404 otherwise).
- Logs pass through a redacting filter; validation errors never echo submitted values.

## Run it locally (simulated broker, any OS)

```bash
git submodule update --init
python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..

cp .env.example .env    # then set: MOHZ_BROKER_KEY=$(cd backend && python -m mohz.keygen)
                        #           MOHZ_CONNECTOR=fake   MOHZ_COOKIE_SECURE=false
cd backend
../.venv/bin/uvicorn mohz.app:app --port 8000 &     # API + built frontend on http://localhost:8000
../.venv/bin/python -m mohz.supervisor              # starts/stops the bots
```

For frontend work, `cd frontend && npm run dev` (Vite on :5173, proxies `/api` to :8000).
With the simulated broker, a password starting with `wrong` fails like a bad login, and a
server name containing `Real` acts as a real-money account.

## Tests

```bash
cd backend && ../.venv/bin/python -m pytest -q    # 31 tests, includes a real supervisor -> worker -> engine run
cd frontend && npm test
```

## Production

MT5 needs Windows: see [docs/DEPLOY.md](docs/DEPLOY.md) (Windows VPS, one portable MT5
terminal per account, Postgres, HTTPS).

## Layout

| path | what |
| --- | --- |
| `engine-src/` | the trading engine (submodule, untouched) |
| `backend/mohz/app.py`, `api/` | HTTP API: auth, accounts, payments, account details, live stream (SSE) |
| `backend/mohz/models.py` | users, sessions, plans, payments, broker_accounts, bot_state, account_snapshot, account_events |
| `backend/mohz/supervisor.py` | one worker per running account, backoff, restore after restart |
| `backend/mohz/worker.py` | the engine on one account |
| `backend/mohz/probe.py` | login test on save + Detect gold symbol, in spare terminals |
| `backend/mohz/settings_map.py` | card settings → engine settings |
| `backend/mohz/connectors/` | real MT5 terminals, or the simulated broker |
| `frontend/` | React + Vite + Tailwind PWA |

## Payments

Model and screen only for now (`payments` table, *Payment history*). To add a provider,
create `Payment` rows from its webhook (`provider` + `provider_ref` are unique together),
set `invoice_url` to its hosted invoice, and switch `users.plan_id` on subscription changes.
