# API Sentinel — Deployment Guide

This guide describes how to deploy API Sentinel to a real environment. It
covers HTTPS, the environment variables, a managed PostgreSQL instance, the
migrations, the health checks and the smoke check after the rollout.

> The application has been verified locally (Docker Compose, PostgreSQL 16,
> the full Playwright walkthrough) **and** live on Render. The live release
> is `https://sentinel-web-ryxl.onrender.com`; the verification output is
> recorded in [implementation-status.md](implementation-status.md#milestone-6--cloud-deployment-render-free-tier--neon).

---

## 0. Render (the deployment used for this release)

This is the concrete, verified path. The live service is
**https://sentinel-web-ryxl.onrender.com**. Render's free tier has no
background worker, no private services and no one-off jobs, so the four
runtimes share a single web-service container as four separate OS
processes:

| Process | Role | Port inside the container |
|---|---|---|
| `uvicorn sentinel.core.app` | Core API | 8000 |
| `uvicorn sentinel.ingest.app` | Ingestion API | 8001 |
| `python -m sentinel.detector.worker` | Detection worker | none |
| `nginx` | The SPA and the same-origin proxy | `$PORT` |

The migration runs first, so the schema owner stays unique:
`alembic upgrade head` is idempotent and a restart is safe.

The browser, the Core API and the Ingestion API share one origin: the nginx
process terminates TLS (Render does that in front of the container), serves the
SPA and proxies `/api/`, `/ingest/` and `/health/` to the two API processes on
the loopback interface.

> The Docker Compose stack in `compose.yaml` keeps the runtimes in separate
> containers and remains the reference deployment shape. The combined image
> exists only because the free tier cannot host a background worker.

### 0.1 Files

| File | Purpose |
|---|---|
| `render.yaml` | The Render Blueprint: one web service and its environment |
| `deploy/Dockerfile.render` | The combined image (Node build stage, Python runtime) |
| `deploy/entrypoint.sh` | Starts the four runtimes and stops them cleanly |
| `frontend/nginx.conf.template` | The nginx configuration, rendered at start |
| `frontend/render-nginx-config.sh` | Renders the template with the environment |

### 0.2 Database

Use [Neon](https://neon.tech) (free, no expiry) or a Render Postgres instance.

1. Create a project and a PostgreSQL 16 database.
2. Copy the **pooled** connection string. It looks like
   `postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require`.
3. Convert the driver to the SQLAlchemy psycopg driver:
   `postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require`.
   The application reads `SENTINEL_DATABASE_URL`.
4. Verify the string before deploying it. The script never prints the
   password:

   ```sh
   backend/.venv/bin/python scripts/check_db.py \
     "postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require"
   ```

   The expected output is `RESULT  : connected`.

> **IPv6 note.** Neon publishes an IPv4 **and** an IPv6 address for the
> pooled endpoint. A runtime without an IPv6 route (the Render free tier, for
> example) resolves the hostname to the IPv6 address and fails with
> `Network is unreachable`. The application resolves the hostname at start-up
> and pins the IPv4 address for libpq (`hostaddr`), while the hostname is
> still sent as `host` so TLS SNI and the certificate verification keep
> working. The same applies to the Alembic migration in
> `backend/alembic/env.py`.

### 0.3 Deploy

1. Push the repository to GitHub. The Blueprint reads `render.yaml` from the
   repository root.
2. In the Render dashboard choose **New → Blueprint**, select the repository
   and confirm the blueprint path `render.yaml`.
3. Render asks for the two secret values:
   - `SENTINEL_DATABASE_URL` — the Neon connection string from step 0.2
   - `SENTINEL_SECRET_KEY` — generate it with
     `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
4. Render creates the service and starts the build. The first build installs
   the pinned Python dependencies and builds the SPA.
5. When the deploy succeeds, open the service URL. The browser must reach the
   SPA and the API on the same host.

### 0.4 Verify the live deployment

```sh
python3 scripts/smoke.py \
  --base-url https://sentinel-web-ryxl.onrender.com \
  --core-url https://sentinel-web-ryxl.onrender.com \
  --ingest-url https://sentinel-web-ryxl.onrender.com
```

The script verifies the browser URL, the Core and Ingest health paths and the
freshness of the detector heartbeat. It exits non-zero when a check fails.

A second script exercises the whole product flow over the public HTTP
surface: it registers an account, creates a workspace and a source, submits
synthetic events through the ingestion endpoint and waits for the detector to
raise the alert.

```sh
backend/.venv/bin/python scripts/live_check.py \
  --base-url https://sentinel-web-ryxl.onrender.com
```

Then open the site, create the first account through the sign-up form and
check the Overview page.

### 0.5 Free-tier limitations to expect

| Limitation | Effect |
|---|---|
| The service spins down after 15 minutes of inactivity | The first request after a quiet period waits for a cold start (about a minute) |
| The Neon free tier has an idle autoscale | The database pauses when unused and resumes on the next query |
| 750 free instance hours per month | The service is suspended when the monthly allowance is used up |
| One instance | No horizontal scaling |

A paid plan removes the spin-down and the autoscale pauses. The blueprint does
not need any change for it.

---

## 1. Target shape

| Component | Recommendation |
|---|---|
| Reverse proxy | Nginx, Caddy, Traefik or a cloud load balancer that terminates TLS |
| Web | The `web` container (nginx serving the built SPA and proxying the API routes) |
| Core API | One or more instances of the `core` container |
| Ingestion API | One or more instances of the `ingest` container |
| Detector | Exactly one `detector` instance in this release |
| Database | A managed PostgreSQL 16 instance with a persistent volume and automated backups |

The `demo` service is **not** deployed to production. It is a local teaching
fixture and it is disabled with `SENTINEL_DEMO_MODE=false`.

---

## 2. TLS and cookies

The browser and the API must share one origin. The simplest shape is a single
public hostname that terminates TLS and routes:

| Path | Target |
|---|---|
| `/` and `/assets/` | The static SPA |
| `/api/` | The Core API |
| `/ingest/` | The Ingestion API (still requires the source credential) |
| `/health/` | The Core API health routes |

In production:

```sh
SENTINEL_APP_ENV=production
SENTINEL_SECURE_COOKIES=true
```

`SENTINEL_SECURE_COOKIES=true` adds the `Secure` attribute to the session and
CSRF cookies, so the session is only sent over HTTPS. The `Secure` attribute
requires HTTPS: do not enable it on a plain-HTTP host, or the browser will
refuse to store the session cookie.

The proxy must also forward the scheme correctly, because the same-origin
check compares the `Origin` header with the `Host` header:

```nginx
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

`$http_host` keeps the port; `$host` would drop it and the same-origin check
would then reject every state-changing browser request.

Limit the request body size at the proxy **and** at the service boundary. The
Core API rejects bodies over 64 KiB and the Ingestion API over 32 KiB before
parsing them.

---

## 3. Environment variables

| Variable | Required | Production value | Description |
|---|---|---|---|
| `SENTINEL_DATABASE_URL` | yes | `postgresql+psycopg://USER:PASSWORD@HOST:5432/DB` | The application database |
| `SENTINEL_SECRET_KEY` | yes | a long random value | Application secret. Rotate it together with a session purge. |
| `SENTINEL_APP_ENV` | yes | `production` | Enables the production behaviour (no API docs, secure cookies) |
| `SENTINEL_SECURE_COOKIES` | yes | `true` | Adds `Secure` to the session cookies |
| `CORE_UPSTREAM` | no | `http://127.0.0.1:8000` | The Core API base URL used by the nginx proxy |
| `INGEST_UPSTREAM` | no | `http://127.0.0.1:8001` | The Ingestion API base URL used by the nginx proxy |
| `SENTINEL_SESSION_TTL_SECONDS` | no | `604800` | Session lifetime |
| `SENTINEL_LOGIN_RATE_LIMIT_PER_MINUTE` | no | `10` | Login attempts per client per minute |
| `SENTINEL_INGESTION_RATE_LIMIT_PER_MINUTE` | no | `600` | Events per source per minute |
| `SENTINEL_TRUSTED_HOSTS` | no | the public hostname | Comma-separated host allowlist |
| `SENTINEL_CORS_ORIGINS` | no | empty | Only needed for a split frontend origin |
| `SENTINEL_DEMO_MODE` | yes | `false` | Disables the demo features in production |
| `SENTINEL_DETECTOR_POLL_INTERVAL_SECONDS` | no | `1.0` | How often the worker polls for jobs |
| `SENTINEL_DETECTOR_MAX_ATTEMPTS` | no | `5` | Attempts before a job is marked failed |

The rule thresholds and windows are documented in
[architecture.md](architecture.md#rule-configuration).

### Generating the secret

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Keep the value out of the repository and out of the logs. Store it in the
platform's secret manager.

---

## 4. Managed PostgreSQL

Use a managed PostgreSQL 16 instance (RDS, Cloud SQL, Azure Database for
PostgreSQL, or a container with a persistent volume). Requirements:

- **Persistent storage** — the database must survive a restart.
- **Automated backups** — the alert and event history is the audit trail.
- **TLS** to the database, with `sslmode=require` in the connection string.
- **No public exposure** — keep it on a private network and allow the
  application subnets only.
- **Connection limits** — each application instance opens a small pool
  (`pool_size=5`, `max_overflow=10`).

The migrations need a role that can create tables and alter them. The
application role needs full access to the same schema.

---

## 5. Migrations

There is exactly **one** migration owner: the `migrate` service. It runs
`alembic upgrade head` and exits.

Run it as a one-off job **before** the application services start, and wait for
it to succeed:

```sh
docker compose run --rm migrate
```

or, in a platform that supports job ordering, define it as an
`init`/`preDeploy` step. The application containers must not start against an
outdated schema.

Alembic reads the database URL from `SENTINEL_DATABASE_URL`, so the migration
job and the services must use the same value.

On a platform without one-off jobs (Render's free tier), the migration runs as
the first step of the container entrypoint. `alembic upgrade head` is
idempotent, so a restart or a redeploy re-runs it safely without duplicating
a revision.

---

## 6. Container images

The repository builds three images from `backend/`, `frontend/` and `demo/`.
Only the first two are deployed:

```sh
docker build -t registry.example.com/sentinel/core:1.0.0 ./backend
docker build -t registry.example.com/sentinel/web:1.0.0 ./frontend
docker build -f deploy/Dockerfile.render -t registry.example.com/sentinel/all:1.0.0 .
```

The `web` image is a multi-stage build: Node 22 builds the SPA and nginx
serves the result. The `backend` image is `python:3.12-slim` with the pinned
dependencies from `backend/pyproject.toml`. The third image combines both
runtimes plus the detection worker for a platform without a background
worker.

Pin the image tags to a release. Do not use `latest` in production.

---

## 7. Health checks

Every service exposes a health endpoint:

| Service | Endpoint | Meaning |
|---|---|---|
| Core | `GET /health/live` | The process is up |
| Core | `GET /health/ready` | The database is reachable |
| Core | `GET /health/detector` | The detector heartbeat is fresh |
| Ingest | `GET /health/live` | The process is up |
| Ingest | `GET /health/ready` | The database is reachable |
| Detector | container probe | The heartbeat in PostgreSQL is under 60 seconds old |

The detector is a worker without an HTTP server, so its container probe runs
`python -m sentinel.detector.healthcheck`, which reads the heartbeat row from
PostgreSQL. Configure the orchestrator to restart the detector when the probe
fails.

The health responses expose no internal details: no host names, no database
names, no job counts.

---

## 8. Rolling out

1. Apply the database migrations.
2. Deploy the Core and Ingest services and wait for them to become healthy.
3. Deploy exactly one detector instance.
4. Deploy the web proxy.
5. Run the smoke check against the live URL.
6. Create the first account through the sign-up form and check the Overview
   page.

### Smoke check against a live deployment

```sh
python3 scripts/smoke.py \
  --base-url https://sentinel.example.com \
  --core-url https://sentinel.example.com \
  --ingest-url https://sentinel.example.com
```

The script verifies that the browser URL serves the SPA, that the Core and
Ingest health paths respond and that the detector heartbeat is fresh. It exits
non-zero when any check fails, so it can be used as a deployment gate.

---

## 9. Backup and recovery

- Enable the managed database's automated backups and test a restore.
- The alert, evidence, comment and history tables are the audit trail and
  should be included in every backup.
- The `security_events` table is the largest one and grows with the traffic.
  Apply the retention procedure from
  [architecture.md](architecture.md#removing-old-events-without-orphaning-evidence)
  on a schedule.
- The session table can be purged safely: the rows are only used to validate a
  live session.

```sql
DELETE FROM sessions WHERE expires_at < now() OR revoked_at IS NOT NULL;
```

---

## 10. Monitoring and operations

| Signal | Where |
|---|---|
| Core errors | The application log of the `core` container |
| Detector failures | `detector_jobs` rows with `status = 'failed'` and `last_error` |
| Detection lag | The age of the `detector_heartbeat.last_seen_at` row |
| Ingestion rejections | The HTTP status codes of `POST /ingest/v1/events` (401 = bad key, 409 = conflicting duplicate, 422 = invalid payload, 429 = rate limited) |
| Disk usage | The managed database volume |

The `detector_jobs` table is the place to look when an alert did not appear.
A `failed` job carries a sanitized `last_error`; requeue it with the manual
recovery statement from
[architecture.md](architecture.md#reliability).

---

## 11. Scaling notes

- **Core and Ingest** are stateless apart from the database and can be scaled
  horizontally behind the proxy.
- **The detector must stay a single instance** in this release. The ordering
  and the concurrency guarantees are only implemented and tested for one
  worker. Running several replicas would require the ordering and the
  concurrent-processing tests described in the architecture document.
- **The database** is the shared bottleneck. When it becomes the limit, the
  first step is to add indexes on the hot filter columns, and the second step
  is to introduce read replicas for the monitoring queries.

---

## 12. Checklist before going live

- [ ] `SENTINEL_APP_ENV=production`
- [ ] `SENTINEL_SECURE_COOKIES=true`
- [ ] `SENTINEL_SECRET_KEY` set to a fresh random value, stored in a secret manager
- [ ] `SENTINEL_DEMO_MODE=false`
- [ ] The demo service is not deployed
- [ ] HTTPS terminates at the proxy and the proxy forwards `Host` and `X-Forwarded-Proto`
- [ ] The request body size is limited at the proxy
- [ ] The database is managed, persistent, backed up and not publicly exposed
- [ ] The migrations ran successfully against the production schema
- [ ] Exactly one detector instance is running
- [ ] The health probes are wired to the orchestrator
- [ ] `python3 scripts/smoke.py --base-url https://sentinel.example.com` passed
- [ ] A real account was created and the Overview page renders real data
