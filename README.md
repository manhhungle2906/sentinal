# API Sentinel

API Sentinel is an API security monitoring and threat detection application for
developers and small teams. It collects request metadata from the APIs you
monitor, applies three explainable detection rules, links every alert to the
events that triggered it, and gives the team a shared investigation workflow.

**What it does not do:** it does not block traffic, it does not scan networks,
it does not try to guess credentials, and it does not claim that an alert is a
confirmed exploit. A source IP is telemetry, never proof of identity.

---

## Architecture at a glance

```
             browser
                │  (same origin, session cookie + CSRF)
                ▼
        ┌───────────────┐        ┌──────────────┐
        │  web (nginx)  │───────▶│  core API    │  auth, workspaces,
        │  reverse proxy│        │  FastAPI     │  sources, monitoring,
        └───────┬───────┘        └──────┬───────┘  alert investigation
                │                       │
                │  POST /ingest/v1/events│
                ▼                       ▼
        ┌──────────────┐        ┌────────────────┐
        │ ingest API   │        │   PostgreSQL 16 │  single migration owner
        │ FastAPI      │◀──────▶│  (one instance)│
        └──────────────┘        └───────┬────────┘
                │                       │
                │                       ▼
                │               ┌──────────────┐
                └──────────────▶│  detector    │  rule evaluation,
                    (events)    │  worker      │  alert + evidence
                                └──────────────┘
```

This is a **service-separated architecture with intentionally shared
persistence**: ingestion and detection are separate workloads with separate
entry points and separate lifecycles, and they can restart independently. They
share one PostgreSQL instance, which means a schema change couples them. That
is a deliberate trade-off for a solo project — database-per-service would add
a migration pipeline, cross-service consistency rules and a second operational
surface for a single-developer codebase.

See [docs/architecture.md](docs/architecture.md) for the full description.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker Desktop | any recent | Docker Compose v2 (`docker compose`, not `docker-compose`) |
| Python | 3.12 | Only for the small orchestration scripts and the test suite |
| Node.js | 22 | Only if you want to run the frontend toolchain outside Docker |

The frontend toolchain runs inside Docker, so Node.js on the host is optional.

---

## Quick start

```sh
# 1. Local configuration (never overwrite an existing .env)
cp .env.example .env

# 2. Validate the Compose file
docker compose --profile demo config --quiet

# 3. Build and start the whole stack
docker compose --profile demo up --build --wait --wait-timeout 120

# 4. Inspect the state
docker compose --profile demo ps -a

# 5. Smoke check
python3 scripts/smoke.py
```

The application is then available at **<http://localhost:8080>**. The proxy is
bound to the loopback interface only, so the stack is not reachable from the
network.

On Windows use `py -3.12` instead of `python3` if `python3` is not available.

### Stopping the stack

```sh
docker compose --profile demo down
```

The PostgreSQL volume is retained, so your local data survives a restart.

---

## Seed the demo data

The demo script creates a demo account, a workspace, an API source and the
synthetic detection scenarios. It only submits to the configured local stack.

```sh
python3 scripts/demo.py --scenario all
```

After it finishes you can sign in with:

| Field | Value |
|---|---|
| Email | `demo-owner@example.com` |
| Password | `demo-owner-password` |

### What the demo seeds

| Scenario | Source IP | Events | Expected alert |
|---|---|---|---|
| `failed_login_burst` | `203.0.113.11` | 5 explicit `login_failed` | High, threshold 5 / 120 s |
| `high_request_volume` | `203.0.113.12` | 101 request events | Medium, threshold 101 / 60 s |
| `repeated_access_denial` | `203.0.113.13` | 10 HTTP 403 responses | Medium, threshold 10 / 300 s |
| under-threshold control | `203.0.113.14/16/17` | 4 / 9 / 100 events | **no alert** |
| normal activity | `203.0.113.15` | 12 requests + 1 denial | **no alert** |

The scenarios are isolated per source IP so each expected alert is
unambiguous. The event identifiers are deterministic (UUIDv5), so a rerun
produces the same records and the ingestion API answers the duplicates with
`200` instead of creating a second event.

The script also sends ordinary requests to the Demo API so genuine telemetry
flows through ingestion and shows up in the Event Explorer.

---

## Repeatable walkthrough

1. Start the stack and run `python3 scripts/demo.py --scenario all`.
2. Sign in at <http://localhost:8080/login> as `demo-owner@example.com`.
3. Select the **Sentinel Demo** workspace in the header selector.
4. Open **Sources** — the *Demo API* source is listed with its key prefix.
5. Open **Events** — the ordinary Demo API request is visible.
6. Open **Alerts** — the three rule types are listed with their counts.
7. Open the `failed_login_burst` alert — the trigger condition, the threshold,
   the window and the linked evidence are shown.
8. Assign the alert to a member from the **Assign to** dropdown.
9. Sign in as a second member in another browser profile and post a comment.
10. Move the alert to *Investigating* and then *Resolved*.
11. Reload the page — the comment, the assignment and the full history are
    still there.

---

## Commands

| Action | Command |
|---|---|
| Local config, once | `cp .env.example .env` |
| Validate Compose | `docker compose --profile demo config --quiet` |
| Start local demo | `docker compose --profile demo up --build --wait --wait-timeout 120` |
| Inspect state | `docker compose --profile demo ps -a` |
| Diagnose a failure | `docker compose --profile demo logs --tail=100 core ingest detector` |
| Smoke check | `python3 scripts/smoke.py` |
| Seed classroom demo | `python3 scripts/demo.py --scenario all` |
| Quick backend checks | `python3 scripts/verify.py --suite backend` |
| Quick frontend checks | `python3 scripts/verify.py --suite frontend` |
| Browser checks | `python3 scripts/verify.py --suite e2e` |
| Full gate | `python3 scripts/verify.py --suite all` |
| Stop without losing local data | `docker compose --profile demo down` |

`scripts/verify.py --suite all` uses an isolated Compose project, an empty
test database and dynamically allocated host ports, and removes only the
resources it created. It never touches your own volumes.

---

## Detection rules

| Rule key | Counted events | Threshold | Window | Severity |
|---|---|---:|---:|---|
| `failed_login_burst` | explicit `login_failed` events | 5 | 2 minutes | High |
| `high_request_volume` | all validated request events, logins included | 101 | 1 minute | Medium |
| `repeated_access_denial` | HTTP 401/403 outside the failed-login stream | 10 | 5 minutes | Medium |

The thresholds and windows are configurable through the environment
(`SENTINEL_FAILED_LOGIN_BURST_THRESHOLD`, `SENTINEL_HIGH_REQUEST_VOLUME_WINDOW_SECONDS`, …).
See [docs/architecture.md](docs/architecture.md#rule-configuration) for the full
list of variables.

**Window semantics.** The counting interval is `(t - window, t]`, where `t` is
the server receipt timestamp of the event being evaluated. The start boundary is
excluded and the end boundary is included. Counting is separated per source id
and per source IP.

**Crossings.** An alert is created only when the count moves from below the
threshold to at-or-above it. After the alert is created, further alerts for the
same rule, source and IP are suppressed for one window. A crossing during the
suppression window is not queued for later delivery — a fresh crossing is
required.

**Delayed batches.** Because the decision uses the server receipt time, a
delayed batch of events reflects its *arrival rate*, not the original
historical traffic rate.

**Dashboard granularity.** The traffic chart uses fixed buckets of **60
seconds**. The Overview page polls every **30 seconds** and offers a manual
refresh. The Alerts page polls every **15 seconds** so a newly detected alert
appears without a reload, and also offers a manual refresh.

---

## Security model

- Passwords are hashed with **Argon2id**.
- Sessions are opaque high-entropy server-side tokens; only a SHA-256 digest
  is stored. The cookie is `HttpOnly` and `SameSite=Lax`, and `Secure` is
  enabled in the HTTPS production configuration.
- State-changing browser routes require a **CSRF token** (double-submit
  cookie plus an `X-CSRF-Token` header) and a same-origin check.
- Access is denied by default: a user outside a workspace gets `404`, a
  member with the wrong role gets `403`, a missing session gets `401`.
- Only an owner or an analyst can be assigned to an alert.
- Request and response bodies, `Authorization` and `Cookie` headers, raw
  passwords and tokens are **never stored**.
- The ingestion endpoint is reachable on the same origin but always requires
  the source credential. Rotating a key invalidates the previous one
  atomically; revoking a key rejects it immediately.
- The Demo API and demo fixtures are disabled in production
  (`SENTINEL_DEMO_MODE=false`).

### What is stored

| Field | Notes |
|---|---|
| Source IP | Telemetry supplied by the authenticated source. Documented in [docs/architecture.md](docs/architecture.md#data-handling). |
| Route template | The template from the instrumented router, never a raw URL path. Query strings and fragments are rejected. |
| Request timestamp | Preserved as evidence; the server receipt timestamp drives the detection decisions. |
| Duration | Optional, non-negative milliseconds. |

To remove old events without orphaning alert evidence, delete the
`alert_evidence` rows that reference them first, then the `security_events`
rows, then the `detector_jobs` rows. `scripts/` documents the exact order.

---

## API surface

| Surface | Operations |
|---|---|
| Core auth | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Core workspaces | `GET/POST /api/workspaces`, `GET/POST /api/workspaces/{id}/members`, `DELETE /api/workspaces/{id}/members/{user_id}` |
| Core sources | `GET/POST /api/sources`, `POST /api/sources/{id}/rotate`, `POST /api/sources/{id}/revoke` |
| Core monitoring | `GET /api/events`, `GET /api/dashboard/stats`, `GET /api/alerts` |
| Core investigation | `GET /api/alerts/{id}`, `PATCH /api/alerts/{id}/status`, `PATCH /api/alerts/{id}/assignee`, `POST/GET /api/alerts/{id}/comments`, `GET /api/alerts/{id}/history`, `GET /api/alerts/{id}/evidence` |
| Ingestion | `POST /ingest/v1/events` — `202` new, `200` identical retry, `409` conflicting duplicate |
| Health | `GET /health/live`, `GET /health/ready` on Core and Ingest, `GET /health/detector` on Core |

The interactive API documentation is available at
<http://localhost:8000/api/docs> in development mode.

---

## Repository layout

```text
frontend/       React 19 + TypeScript + Vite + Tailwind + Recharts, and Playwright tests
backend/
  sentinel/core/    Core API (auth, workspaces, sources, monitoring, investigation)
  sentinel/ingest/  Ingestion API
  sentinel/detector/ Rule engine and background worker
  sentinel/common/  DB session, models, contracts, security helpers
  alembic/          The single migration owner
tests/          Unit and PostgreSQL integration tests
demo/           Demo API and the synthetic fixture generator
scripts/        Setup, verification and demo entry points
docs/           Architecture, deployment, demo and progress
compose.yaml    The local stack
```

---

## Documentation

| Document | Content |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Services, data model, rule semantics, configuration, data handling |
| [docs/deployment.md](docs/deployment.md) | HTTPS, environment variables, managed database, migrations, health and smoke checks |
| [docs/implementation-status.md](docs/implementation-status.md) | Milestones and the actual result of every verification command |

---

## Known limitations

- The detector runs as a single worker process. Worker replicas are not
  implemented, so the ordering guarantees are only tested for one instance.
- Manual detection rules cannot be edited from the UI; the thresholds come from
  the environment configuration.
- There are no external notifications (email, chat) in this release.
- There is no SSO, no machine-learning detection and no automatic blocking.
