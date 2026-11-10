# KingOfFreight

Phase-1 single-broker freight operations app for a single freight broker.

## Run locally

Requirements: Python 3.10, Node.js 20 with npm, Docker with Compose, and (for
local non-container execution) a PostgreSQL server.

```sh
cp .env.example .env
docker compose up -d db
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
```

In a second terminal, start the Vite frontend:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to the backend on port 8000 so
the signed session cookie remains same-origin.

### Accounts and KOF data sync

Set `BOOTSTRAP_USERNAME` to create the initial named user on application
startup. That user's first login uses the configured `BROKER_PASSWORD` and
requires a personal password of at least 10 characters before accessing other
API routes. Later logins use the personal password. The legacy login with a
blank username and `BROKER_PASSWORD` remains available for the existing broker
account flow.

KOF sync is read-only: it signs in to the authorized intranet modules, reads
list pages, and stores loads and sales-list snapshots in PostgreSQL. Set
`KOF_USERNAME` and `KOF_PASSWORD` to configure the site account, or enter the
KOF login in Settings instead. Environment credentials require
`KOF_SYNC_ENABLED=true`; credentials saved in Settings enable scheduled sync
when `SCHEDULER_ENABLED=true`. The scheduler runs incremental syncs at
`KOF_SYNC_INTERVAL_MINUTES` intervals and a full sync at
`KOF_FULL_SYNC_HOUR_UTC`. An authenticated broker can also start a full or
incremental sync with `POST /api/kof/sync?kind=full` or
`POST /api/kof/sync?kind=incremental`. `GET /api/kof/sync` reports status.

See [DESIGN.md](DESIGN.md) for frontend brand, theme, layout, and accessibility conventions.

Run the app as a single Uvicorn worker and a single instance. The in-process
scheduler would otherwise run duplicate check-in jobs and double-send messages.

For the integrated production-style service, run `docker compose up --build`
from the repository root. The multi-stage image builds the React app and serves
it from FastAPI, applies Alembic migrations, and then starts Uvicorn. To seed
the container database separately, run:

```sh
docker compose exec backend python -m scripts.seed
```

### Deploy on Render

Connect this GitHub repository in Render, choose **New → Blueprint**, select the
repository, set `BROKER_PASSWORD` and `BOOTSTRAP_USERNAME`, and deploy. The Blueprint
creates a paid Render Postgres database and a single always-on web instance. It
temporarily keeps the legacy uploads disk and `UPLOAD_DIR` setting so the first
deploy can migrate existing BOL PDFs into Postgres. The first deploy fails and
Render keeps the previous version running (if any) when a stored PDF cannot be
found; mount the old uploads disk and set `UPLOAD_DIR`, or set
`BOL_BACKFILL_ALLOW_MISSING=true` to proceed without missing PDFs. After the
migration succeeds, the disk can be removed. It builds the frontend into the
backend Docker image and runs Alembic migrations at startup.

After deployment, configure the Twilio inbound SMS webhook as
`https://<render-url>/api/webhooks/twilio/sms`. To enable live integrations,
add the provider credentials under the web service's Environment settings:
`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`,
`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_MAILBOX`,
`ANTHROPIC_API_KEY`, and `FMCSA_WEBKEY`, along with the corresponding provider
selectors (`SMS_PROVIDER`, `EMAIL_PROVIDER`, `LLM_PROVIDER`, and
`FMCSA_PROVIDER`). Email and FMCSA default to mock. SMS defaults to `auto`:
complete Twilio settings saved in the app (preferred) or env enable real texting;
otherwise SMS is mocked. Set `SMS_PROVIDER=mock` to explicitly disable live SMS.
LLM selection defaults
to `auto`: a key saved in Settings (preferred) or `ANTHROPIC_API_KEY` enables
Anthropic for BOL extraction and driver-reply parsing; no key uses the mock.
Set `LLM_PROVIDER=mock` to explicitly disable Anthropic for those features.

While signed in, open `/api/integrations/status` to see the selected `llm` and
`sms` providers and `twilio_configured` without exposing credentials.
`twilio_configured` means all three Twilio settings are nonblank, not that
Twilio has validated them. The LLM status describes selection, not live health;
Anthropic request failures fall back to local mock processing.

For a manual Docker deployment, build from the repository root with
`docker build -f backend/Dockerfile -t kingoffreight .`. Set `DATABASE_URL`,
`BROKER_PASSWORD`, and `SECRET_KEY`; the container uses the platform `PORT`
when provided and serves both the API and built frontend.

### Deploy anywhere

Any container host can build the single-service image from the repository root
with `docker build -f backend/Dockerfile -t kingoffreight .`. At startup the
container runs `alembic upgrade head` and listens on `$PORT`. Use exactly one
instance and one Uvicorn worker because the scheduler runs in-process. The app
requires PostgreSQL 14 or newer and no other persistent storage; uploaded BOL
PDFs are stored in PostgreSQL.

Set these required environment variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection URL; `postgres://`, `postgresql://`, and `postgresql+psycopg://` are accepted |
| `BROKER_PASSWORD` | Bootstrap and legacy broker login password |
| `SECRET_KEY` | Random value of at least 32 characters; generate one with `openssl rand -base64 32` |
| `ENV` | Set to `production` |
| `PUBLIC_BASE_URL` | Public HTTPS URL for driver tracking links; defaults to Render's service URL on Render |

Optional live provider settings and their credentials:

| Integration | Settings |
|---|---|
| Twilio SMS | `SMS_PROVIDER=auto` (default) or `twilio`; save Account SID, Auth Token and From number in Settings, or set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` |
| Microsoft Graph email | `EMAIL_PROVIDER=graph`, `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_MAILBOX` |
| Anthropic LLM | `LLM_PROVIDER=auto` (default) or `anthropic`; save a key in Settings or set `ANTHROPIC_API_KEY` (optional `ANTHROPIC_MODEL`) |
| FMCSA carrier verification | `FMCSA_PROVIDER=live`, `FMCSA_WEBKEY` |

For Twilio, set the inbound SMS webhook to
`https://<render-url>/api/webhooks/twilio/sms`.

Settings → Texting (Twilio) shows the webhook URL with a copy button. Paste it
under Phone Number → Messaging → "A message comes in" and select HTTP POST.
The Auth Token is encrypted with `SECRET_KEY`; saved settings override the env
credentials as a complete set. Removing them falls back to env credentials.
The test button sends one real SMS with resolved credentials even in mock mode.
Twilio accepting a message does not guarantee delivery (trial accounts and
messaging-registration requirements may apply).

Authenticated API: `GET/PUT/DELETE /api/integrations/twilio/connection` and
`POST /api/integrations/twilio/test` with `{ "to": "+15551234567" }`.
Connection responses expose masked SID/from number, configuration/source and SMS
mode, never the token. `PUT` requires all three fields: `account_sid`,
`auth_token`, `from_number` (E.164). Signature validation uses an explicitly set
`PUBLIC_BASE_URL`; otherwise it reconstructs the public URL using forwarded
protocol/host headers. Configure the proxy to supply accurate forwarded headers.

To move between database hosts, dump and restore the database:

```sh
pg_dump -Fc "$OLD_URL" > kof.dump
pg_restore --no-owner -d "$NEW_URL" kof.dump
```

The dump includes BOL PDFs. After moving, update the Twilio webhook URL and
`PUBLIC_BASE_URL`.

The demo broker password is `changeme`; replace it before exposing the service.
The API is at `http://localhost:8000`, with health check `/health`. OpenAPI docs
are available at `/docs`. `POST /api/auth/login` accepts a password and an
optional username; named users created from `BOOTSTRAP_USERNAME` set a personal
password on first login. A blank username retains the legacy broker-password
login. The signed httpOnly session cookie is used for broker routes. Public
driver tracking and provider webhooks do not require broker auth.

## Environment variables

All settings can be supplied in `.env` or as environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://freight:freight@localhost:5432/freight` | SQLAlchemy database URL (SQLite is supported for tests) |
| `BROKER_PASSWORD` | **required** (`changeme` in `.env.example`) | Bootstrap and legacy broker login password |
| `BOOTSTRAP_USERNAME` | empty | Create this named user at startup; first login uses `BROKER_PASSWORD` |
| `SECRET_KEY` | development placeholder | Signing key; production requires a random value at least 32 characters long |
| `BROKER_NAME` | `Freight Broker` | Name in status emails |
| `BROKER_COMPANY` | `Freight Brokerage` | Company name in messages and tracking |
| `BROKER_TIMEZONE` | `America/Chicago` | Interpret naive UI/BOL datetimes; format ETA |
| `PUBLIC_BASE_URL` | Render service URL or `http://localhost:8000` | Public base URL for tracking links and Twilio signatures |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed browser origins |
| `CHECKIN_OFFSET_MINUTES` | `60` | Default appointment-relative driver check-in offset |
| `NO_REPLY_ALERT_MINUTES` | `30` | Time after a sent check-in before an alert opens |
| `CHECKIN_DEFAULT_CHANNEL` | `sms` | Default driver check-in channel (`sms` or `email`) |
| `SCHEDULER_ENABLED` | `true` | Enable in-process check-in and inbox scheduler |
| `SCHEDULER_INTERVAL_SECONDS` | `60` | Scheduler interval |
| `KOF_SYNC_ENABLED` | `false` | Enable scheduled KOF synchronization for environment credentials |
| `KOF_USERNAME` | empty | KOF intranet username |
| `KOF_PASSWORD` | empty | KOF intranet password |
| `KOF_BASE_URL` | `https://kingsoffreight.com/` | KOF intranet base URL |
| `KOF_SYNC_INTERVAL_MINUTES` | `15` | Incremental sync interval when credentials and scheduler are enabled |
| `KOF_FULL_SYNC_HOUR_UTC` | `8` | UTC hour for the daily full sync |
| `ENV` | `development` | Dev simulation endpoints mount only in development |
| `SMS_PROVIDER` | `auto` | `auto`: Twilio with complete app/env credentials, otherwise mock. Explicit `mock` disables live scheduled SMS; explicit `twilio` selects Twilio. |
| `TWILIO_ACCOUNT_SID` | empty | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | empty | Twilio token and webhook signature validation |
| `TWILIO_FROM_NUMBER` | empty | Twilio sender number |
| `EMAIL_PROVIDER` | `mock` | `mock` or Microsoft Graph `graph` |
| `GRAPH_TENANT_ID` | empty | Entra tenant ID |
| `GRAPH_CLIENT_ID` | empty | Graph client application ID |
| `GRAPH_CLIENT_SECRET` | empty | Graph client secret |
| `GRAPH_MAILBOX` | empty | Broker mailbox UPN |
| `LLM_PROVIDER` | `auto` | `auto`: Anthropic when a saved app key or env key exists, otherwise mock. Explicit `mock` disables Anthropic; `anthropic` uses it when configured, otherwise falls back to mock. App keys take precedence. |
| `ANTHROPIC_API_KEY` | empty | Anthropic API key |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | Anthropic model name |
| `FMCSA_PROVIDER` | `mock` | `mock` or live QCMobile `live` |
| `FMCSA_WEBKEY` | empty | FMCSA QCMobile API key |

## Integration modes

Without credentials, defaults are safe for local development: SMS is mocked (no network), email is
mocked (send is recorded in the app; inbox fetch returns no mail), LLM extraction
and reply parsing use local PDF/text heuristics, and FMCSA returns deterministic
fixtures for MC `123456`, `222222`, `333333`, and `444444`. Outbound provider
communications are logged in the application database in both mock and live
modes.

Live SMS uses the Twilio SDK and validates signed inbound webhooks. Live email
uses Microsoft Graph client credentials to send and poll the broker inbox for
PDF BOLs and load-related replies. Live LLM mode submits PDF document blocks to
Anthropic using the checked-in prompts and forced tool calls. Live FMCSA calls
QCMobile docket, carrier, and authority endpoints. Its response field mapping
is defensive and best-effort; the FMCSA response shapes and field names have
not been verified against a live key. Use mock mode unless provider credentials
and access have been configured.

## Tests and lint

Frontend development checks:

```sh
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build
```

Backend tests and lint:

```sh
cd backend
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest -q
```

The pytest suite uses an in-memory SQLite database. For development, migrations
are managed with Alembic; to create future revisions use
`alembic revision --autogenerate -m "description"` and inspect the generated
revision before applying it.