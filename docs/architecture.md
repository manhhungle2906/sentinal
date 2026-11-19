# API Sentinel — Architecture

This document explains how the system is put together, why it is shaped this
way, and how the detection rules behave.

---

## 1. Service boundaries

| Runtime | Responsibility | Boundary |
|---|---|---|
| Frontend + reverse proxy | Serve the React application and forward the approved Core routes under the same browser origin | No direct database access and no ingestion credentials |
| Core API | Registration, sessions, workspaces, source management, read APIs, alert investigation | Validates membership and role on the server |
| Ingestion API | Authenticate API sources, validate and persist request events | An independent FastAPI process and container |
| Detection worker | Claim persisted events, evaluate the rules, write the alert evidence | An independent process with restart-safe database work |
| PostgreSQL | Durable application data and worker coordination | One instance, one migration owner |
| Demo API | Emit sanitized metadata for ordinary demo requests | An optional Compose profile, local fixtures only |

Each runtime has its own entry point and its own business logic. The only
shared code is `backend/sentinel/common/`, which holds the stable contracts
(the Pydantic DTOs), the persistence definitions (the SQLAlchemy models) and
the session factory. Nothing in `common/` contains route or rule logic.

### Service-separated, intentionally shared persistence

Ingestion and detection are **separate workloads**: they have separate
processes, separate containers, separate health checks and separate restart
lifecycles. The ingestion API can be scaled and restarted without touching the
detector, and the detector can lag behind without blocking ingestion — an
ingestion response confirms persistence, not that the analysis has run.

They nevertheless **share one PostgreSQL database**, which couples them
through the schema: a change to `security_events` or `alerts` requires a
coordinated migration and a coordinated deploy of the two services.

This is a deliberate compromise for a single-developer project:

- **Against database-per-service:** it would require a migration for every
  schema change, a mechanism to keep the alert and evidence data consistent
  across two databases, cross-service queries for the dashboard aggregates, and
  a second operational surface to maintain and monitor. For one team and one
  schema, that is a large amount of machinery for a small amount of isolation.
- **For shared persistence:** the schema is the single source of truth, the
  alert and its evidence live in the same transaction as the event, and the
  dashboard aggregates are plain SQL joins. The isolation that actually matters
  here — process failure, restart, independent scaling — is achieved with
  separate workloads and separate entry points.

If the project later needs independent schema lifecycles, the migration path is
clear: extract the ingestion-owned tables into their own database first, then
publish the events through a contract.

---

## 2. Data model

| Table | Purpose |
|---|---|
| `users` | Accounts with an Argon2id password hash |
| `sessions` | Opaque session tokens (digest only), CSRF digest, expiry and revocation |
| `workspaces` | The tenant boundary for sources, events and alerts |
| `memberships` | User ↔ workspace with the `owner`, `analyst` or `viewer` role |
| `api_sources` | A monitored API, its label, the key digest, the key prefix and the revocation state |
| `security_events` | The persisted request metadata, with `ingest_seq` as the stable tie-breaker |
| `detector_jobs` | One pending/done/failed job per event |
| `alerts` | The finding, the frozen trigger snapshot and the suppression window |
| `alert_evidence` | The link between an alert and the events that were counted |
| `alert_comments` | The investigation comments |
| `alert_history` | The status and assignment changes, with the actor and the timestamp |
| `detector_heartbeat` | A single row with the last detector heartbeat |

### Invariants

- The uniqueness constraint on `(source_id, event_uuid)` makes a retried event
  idempotent: a retry never creates a second event or a second job.
- The event and its detector job are inserted in **one transaction**, so an
  accepted event always has a job and a job never points at a missing event.
- The uniqueness constraint on `(rule_key, trigger_event_id)` makes the alert
  creation idempotent across worker retries.
- Evidence rows are filtered by the alert's own `source_id` when they are read,
  so evidence can never cross a workspace or source boundary.
- Event lookups are indexed by source, source IP and receipt time; list
  queries are indexed by workspace and the filter/time columns and use a
  stable sort with an ID tie-breaker.
- Pagination is bounded (`limit` between 1 and 200) on every list endpoint.

---

## 3. Detection semantics

### The window

The counting interval for a rule is the half-open interval `(t - window, t]`,
where `t` is the **server receipt timestamp** of the event being evaluated.

```python
def in_detection_window(received_at: datetime, as_of: datetime, window: timedelta) -> bool:
    return as_of - window < received_at <= as_of
```

The start boundary is excluded and the end boundary is included.

### Counting is separated per source and per IP

Two events only contribute to the same count when they share the source id
**and** the source IP. A burst from one IP never inflates the count for
another IP, and a second monitored API never inflates the count for the first.

### Equal receipt timestamps

Events that share a receipt timestamp are ordered by the monotonic
`ingest_seq` column. When the window end equals the trigger's receipt
timestamp, only the rows up to the trigger's sequence are counted, so the
worker and the event query always agree on the same stable order.

### Crossing detection

The rule engine computes the count **before** and **after** the current
qualifying event is included:

```text
count_before = count_after - 1        (when the trigger qualifies)
triggered    = count_before < threshold <= count_after
```

An alert is therefore created only on a fresh crossing from below the
threshold to at-or-above it.

### Suppression

When an alert is created, `suppressed_until` is set to the trigger's receipt
timestamp plus one rule window. While that window is open, further crossings
for the same `(rule_key, source_id, source_ip)` are suppressed.

- A crossing **during** the suppression window is not queued for later
  delivery; it is dropped.
- After the window expires, a **fresh crossing** is required to raise a new
  alert.
- Human resolution is independent of detection: resolving an alert does not
  reset the suppression window.

### Delayed batches

The decision uses the server receipt timestamp, not the client timestamp. A
batch that arrives late is therefore evaluated as a burst of arrivals, so the
alert reflects the arrival rate and not the original historical traffic rate.
The client timestamp is preserved on the event as evidence.

### Rule configuration

Every threshold, window and severity comes from the environment. The defaults
are the classroom demo values.

| Variable | Default | Meaning |
|---|---:|---|
| `SENTINEL_FAILED_LOGIN_BURST_THRESHOLD` | 5 | `failed_login_burst` count |
| `SENTINEL_FAILED_LOGIN_BURST_WINDOW_SECONDS` | 120 | `failed_login_burst` window |
| `SENTINEL_FAILED_LOGIN_BURST_SEVERITY` | high | `failed_login_burst` severity |
| `SENTINEL_HIGH_REQUEST_VOLUME_THRESHOLD` | 101 | `high_request_volume` count |
| `SENTINEL_HIGH_REQUEST_VOLUME_WINDOW_SECONDS` | 60 | `high_request_volume` window |
| `SENTINEL_HIGH_REQUEST_VOLUME_SEVERITY` | medium | `high_request_volume` severity |
| `SENTINEL_REPEATED_ACCESS_DENIAL_THRESHOLD` | 10 | `repeated_access_denial` count |
| `SENTINEL_REPEATED_ACCESS_DENIAL_WINDOW_SECONDS` | 300 | `repeated_access_denial` window |
| `SENTINEL_REPEATED_ACCESS_DENIAL_SEVERITY` | medium | `repeated_access_denial` severity |

### Reliability

- The worker claims pending jobs with `SELECT … FOR UPDATE SKIP LOCKED` and
  processes them in a stable receipt order.
- The rule decision, the alert, the evidence links and the job completion are
  written in **one transaction**.
- On a transient failure the transaction is rolled back, the job stays
  `pending`, the attempt counter is incremented and the worker retries with an
  exponential backoff capped at 30 seconds.
- After `SENTINEL_DETECTOR_MAX_ATTEMPTS` (default 5) the job is marked
  `failed` with a sanitized message (`TypeName: processing failed`) — never a
  payload and never a credential.

**Manual recovery.** A failed job is requeued with:

```sql
UPDATE detector_jobs
SET status = 'pending', attempts = 0, last_error = NULL
WHERE id = '<job id>';
```

The alert creation is idempotent, so a requeued job cannot create a duplicate
alert: the unique constraint on `(rule_key, trigger_event_id)` blocks it.

---

## 4. Authentication and authorization

- **Passwords** are hashed with Argon2id (`argon2-cffi`).
- **Sessions** are opaque, high-entropy server-side tokens. Only the SHA-256
  digest is stored in `sessions`. The raw token lives in the `sentinel_session`
  cookie (`HttpOnly`, `SameSite=Lax`, `Secure` in production). Logout revokes
  the row; an expired or revoked session is rejected.
- **CSRF** uses a double-submit cookie: the readable `sentinel_csrf` cookie
  must be echoed in the `X-CSRF-Token` header, and the stored digest must
  match. A same-origin check on the `Origin` header is applied to
  state-changing routes as well. Non-browser clients that omit `Origin` still
  need the CSRF token.
- **Roles**: `owner`, `analyst` and `viewer`.
  - Owners manage the members and the sources, and can investigate.
  - Analysts can read the workspace data and investigate.
  - Viewers can read the workspace data but cannot comment, assign, change a
    status or manage the settings.
- **Status codes**: `401` for a missing or invalid session, `403` for a
  disallowed role inside a workspace, `404` for an object the caller cannot
  reach. A user outside a workspace never learns that the object exists.
- **Forwarding headers** are never trusted for identity. The `source_ip` of an
  event is telemetry supplied by the authenticated source, not an
  authorization input.
- **Rate limits**: the login endpoint allows 10 attempts per minute per client
  (`SENTINEL_LOGIN_RATE_LIMIT_PER_MINUTE`), and the ingestion endpoint allows
  600 events per minute per source
  (`SENTINEL_INGESTION_RATE_LIMIT_PER_MINUTE`). Both are configurable.

---

## 5. Data handling

### What is stored

Only an explicitly allowed set of metadata reaches the database:

| Field | Type | Notes |
|---|---|---|
| `source_id` | UUID | Derived from the authenticated source, never from the payload |
| `event_uuid` | UUID | The caller-supplied event identifier |
| `received_at` | timestamptz | The server receipt timestamp (UTC) |
| `request_at` | timestamptz | The caller-supplied request timestamp (UTC, timezone-aware) |
| `source_ip` | inet | The caller-supplied client IP as seen by the source |
| `route_template` | varchar(255) | The template from the instrumented router |
| `method` | varchar(10) | Uppercase, from the allowed list |
| `status_code` | int | Between 100 and 599 |
| `duration_ms` | int | Optional, non-negative, at most one hour |
| `event_type` | varchar | `request` or `login_failed` |

### What is never stored

Request and response bodies, `Authorization` and `Cookie` headers, raw
passwords, ingestion keys and session tokens are never persisted. The
ingestion contract uses `extra="forbid"`, so an unexpected field is rejected
rather than silently ignored.

### Removing old events without orphaning evidence

Alert evidence and detection jobs both reference the events, so the rows must
be removed in dependency order inside one transaction:

```sql
BEGIN;

-- 1. Drop the evidence links of the events that are going away.
DELETE FROM alert_evidence
WHERE event_id IN (SELECT id FROM security_events WHERE received_at < :cutoff);

-- 2. Drop the detection jobs of those events.
DELETE FROM detector_jobs
WHERE event_id IN (SELECT id FROM security_events WHERE received_at < :cutoff);

-- 3. Drop the events themselves.
DELETE FROM security_events WHERE received_at < :cutoff;

COMMIT;
```

The order matters: the evidence and the jobs reference the event, so they go
first. The alerts themselves are kept, so the finding record and its frozen
threshold snapshot survive; only the evidence links are removed and the alert
detail shows an empty evidence list.

### IP metadata

The source IP is stored so that a burst can be counted per IP and so that an
investigator can see where the traffic came from. It is telemetry, and it is
only as trustworthy as the monitored API. An operator who needs to honour a
retention policy can apply the deletion above on a schedule.

---

## 6. Frontend behaviour

- **Polling**: the Overview page polls every 30 seconds and has a manual
  refresh button. The alerts and events pages refresh on demand.
- **Buckets**: the traffic chart uses a fixed 60-second granularity. The
  buckets are zero-filled over the whole requested range, so a quiet interval
  is visible as a gap rather than a missing bar.
- **Counts**: the dashboard counts requests, failed logins and access denials
  from the events table. Alerts are **not** counted as requests, and
  overlapping alert evidence is **not** summed into a request count.
- **States**: loading, error and empty states are distinct everywhere, and
  the error state always shows the reason. A failed refresh shows an honest
  banner instead of silently keeping stale data.
- **Accessability**: every control has a label, the tables use scoped column
  headers, status is shown as text in addition to colour, and the layout is
  responsive.

---

## 7. Deployment shape

The Compose file is the development shape. The production shape is described
in [deployment.md](deployment.md): the same four application services plus a
managed PostgreSQL instance, behind an HTTPS reverse proxy, with the
migrations run as a one-off job before the services start.

---

## 8. Known trade-offs

| Decision | Trade-off |
|---|---|
| Shared PostgreSQL | Simpler schema and consistent aggregates, at the cost of coupled schema migrations. |
| Single detector worker | Deterministic ordering and simple reasoning; no horizontal scaling of the detection path. |
| Opaque sessions in the database | Revocable and inspectable, but the session table grows with the session TTL. |
| Fixed 60-second dashboard buckets | Stable and cheap to query; a burst inside one minute is not visible as a separate spike. |
| No external notifications | Fewer moving parts; the team has to open the dashboard to see new alerts. |
