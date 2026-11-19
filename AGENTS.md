# AGENTS.md — API Sentinel

**Project:** API Sentinel — API Security Monitoring and Threat Detection  
**Project member:** Hung Manh Le  
**Intended repository:** https://github.com/manhhungle2906/sentinal.git  
**Role:** You are the full-stack implementation and verification agent for API Sentinel, working in Cursor on the local repository.  
**Primary goal:** Deliver a working, tested application, not just a plan or scaffold.

## Lệnh khởi động cho Cursor Agent

Khi bắt đầu hoặc tiếp tục triển khai, hãy dùng yêu cầu sau. Đoạn này không thay thế các tiêu chí kiểm thử bên dưới.

```text
Đọc toàn bộ @AGENTS.md và triển khai API Sentinel ngay trong repository này.
Giữ nguyên các thay đổi hiện có của tôi. Bắt đầu bằng lệnh kiểm tra repo,
sau đó code, chạy app và tự sửa các lỗi tái hiện được theo từng mốc.
Ghi kết quả thực tế vào docs/implementation-status.md và chỉ báo hoàn
thành khi các mục kiểm thử bắt buộc trong Definition of Done đã đạt.
Không tự push hoặc deploy.
```

## 1. Commands and first-run contract

Run from the repository root. On macOS, open the repo in Cursor and use its Terminal. Docker Desktop or another working Docker Compose runtime must already be running for container checks. A host Python 3.12 interpreter runs the small orchestration scripts. Node and PostgreSQL may run entirely in containers.

**Run these checks before editing.** If the folder is not a Git checkout yet, record that and continue without altering remotes.

```sh
git status --short --branch
git diff --stat
git diff --cached --stat
docker compose version
docker info --format '{{.ServerVersion}}'
python3 --version
```

**Target commands for the repo you deliver.** First read existing Makefiles, scripts, dependency manifests, and CI. If equivalent working commands already exist, retain them and update this table and README to match. If a command below does not exist, implement it during the corresponding milestone. Do not report these commands as available or passed before running them.

| Action | Command | Expected result |
|---|---|---|
| Local config, once | `cp .env.example .env` | Local-only defaults are configured. Use `Copy-Item .env.example .env` in PowerShell. Never overwrite an existing `.env`. |
| Validate Compose | `docker compose --profile demo config --quiet` | Exit 0 without printing interpolated secrets. |
| Start local demo | `docker compose --profile demo up --build --wait --wait-timeout 120` | Migration completes, services start, and the frontend is ready. |
| Inspect state | `docker compose --profile demo ps -a` | Migration exits 0 and expected long-running services are healthy. |
| Diagnose a failure | `docker compose --profile demo logs --tail=100 core ingest detector` | Relevant logs show service and failure context without secrets. |
| Smoke check | `python3 scripts/smoke.py` | Default browser URL and Core/Ingest health paths respond, and the detector heartbeat is fresh. |
| Seed classroom demo | `python3 scripts/demo.py --scenario all` | Only local demo fixtures are submitted and the expected three rule types appear on a fresh demo stack. |
| Quick backend checks | `python3 scripts/verify.py --suite backend` | Ruff format/lint and pytest unit + PostgreSQL integration tests run. |
| Quick frontend checks | `python3 scripts/verify.py --suite frontend` | Locked install, lint, typecheck, unit tests and production build run. |
| Browser checks | `python3 scripts/verify.py --suite e2e` | Playwright runs against a real local test stack and reports a trace path on failure. |
| Full gate | `python3 scripts/verify.py --suite all` | Clean DB migration, backend, frontend, smoke, and browser checks actually run. Exit nonzero if any required step fails. |
| Stop without losing local data | `docker compose --profile demo down` | Containers stop. Persistent volumes are retained. |

In a fresh implementation, use Compose service names `web`, `core`, `ingest`, `detector`, `db`, `migrate`, and `demo`. Default development entry point is `http://localhost:8080`. Bind the developer-facing proxy to loopback. Use same-origin proxy routes for Core and, only where needed, the documented ingestion entry point. Document whether ingestion is reachable only inside Compose or through a separately exposed authenticated route. Use the same route choices in the demo and smoke commands.

Implement the Python entry points as small, noninteractive wrappers. Use the existing script architecture if it already supports these checks. `verify.py` should print each command and its exit status, use an isolated Compose project, an empty test DB and separate or dynamically allocated host ports for full verification, and clean up only resources it created. Do not reuse the operator's data or expose the test server publicly. Use containers for toolchains if host runtimes are missing. Make verification callable in CI and from macOS, Windows and Linux. On Windows use `py -3.12` if `python3` is not available.

## 2. Start here

When asked to implement this specification, start editing and running the project. Do not stop after listing steps or generating starter code. Continue across milestones until the local Definition of Done is met or a genuine blocker prevents further work. For routine implementation choices, make a reasonable decision, record it when it affects the design, and continue.

1. Check the current directory, repository root, git status, existing instructions, README, dependency manifests, migrations, tests, existing Cursor rules, and available runtimes. Do not assume the repository is empty. Do not overwrite existing work or change git remotes.
2. Reuse compatible existing code, naming, dependencies, and working tests. Start from the architecture below if the repository is empty. If an existing choice conflicts with a required behavior, make the smallest change that preserves the requirement and document the trade-off.
3. Maintain a short `docs/implementation-status.md` with milestones, next actions, command results, and blockers. Resume from the first unfinished checkpoint if the session ends. This file is not a substitute for code or tests.
4. Verify claims with actual commands and, for the main user flow, an actual browser test. No placeholder business logic, hard-coded dashboard totals, unconnected buttons, fake pass statuses, or TODOs on the required path.

## 3. Product and scope

API Sentinel helps developers and small teams see what happened to their APIs, why a risk alert appeared, and how the team investigated it. It collects request metadata, applies explainable rules, links alerts to event evidence, and supports a shared investigation workflow. It monitors and reports. It does not block traffic or attempt to determine whether a vulnerability is exploitable.

**Required release:** account registration and login, team/workspace access, monitored API sources with ingestion keys, a PostgreSQL-backed event pipeline, three automated rules, an interactive dashboard, event filtering, alert details with evidence, comments, assignment, investigation history, and resolving or dismissing alerts. Include a demonstration API, repeatable demo data, Docker Compose, automated tests, CI configuration, and cloud deployment instructions.

**Out of scope:** automatic blocking, offensive tooling, network scanners, credential guessing, replaying live attacks, third-party target probing, external notifications, SSO, machine-learning detection, and self-service rule editing. Show rule thresholds in alert details and document how to configure defaults. Do not add features outside the required release before the acceptance checks pass.

## 4. Architecture

Baseline for an empty repository: Python 3.12, FastAPI with Pydantic 2, SQLAlchemy 2 and Alembic, PostgreSQL 16, and Node.js 22 with React 19, TypeScript 5, Vite, Tailwind CSS and Recharts. These are development targets, not claims about dependencies already installed. Preserve compatible versions in an existing repo, pin the selected exact dependencies via the Python dependency lock/constraints and npm lockfile, and align Docker images and CI with the selected runtimes. Use Docker Compose v2 for local startup, Ruff and pytest for Python checks, ESLint and Vitest for frontend checks, and Playwright for browser verification. Avoid introducing a broker or additional datastore just for this project.

| Runtime | Responsibility | Boundary |
|---|---|---|
| Frontend + reverse proxy | Serve React and forward approved Core API routes under the same browser origin | No direct DB access or ingestion credentials |
| Core API | Registration, sessions, workspaces, source management, read APIs, alert investigation | Validates membership and role on the server |
| Ingestion API | Authenticate API sources, validate and persist request events | Independent FastAPI process and container |
| Detection worker | Claim persisted events, evaluate rules, write alert evidence | Independent process and container with restart-safe DB work |
| PostgreSQL | Durable application data and worker coordination | One instance to keep the single-developer project maintainable |
| Demo API | Emit sanitized metadata for ordinary demo requests | Optional Compose demo profile and local test fixture input |

Use separately runnable containers and keep each runtime's entry point and business logic distinct. Maintain one migration owner. Use a shared package only for stable contracts or persistence definitions. In the architecture document, explain that ingestion and detection have separate workloads and can restart independently, while the shared PostgreSQL database couples schema changes. Describe it as a **service-separated architecture with intentionally shared persistence**, not a database-per-service system. Describe why this is a practical compromise for a solo project.

Suggested layout, adapted to an existing repository if needed:

```text
frontend/                  React app and browser tests
backend/
  sentinel/core/           Core API
  sentinel/ingest/         Ingestion API
  sentinel/detector/       Worker and rule evaluation
  sentinel/common/         DB session, models and contracts
  migrations/              Alembic
  tests/                   Unit and PostgreSQL integration tests
demo/                     Demo API and synthetic fixture generator
scripts/                  Setup, verification and demo entry points
docs/                     Architecture, deployment, demo and progress
compose.yaml
.env.example
README.md
.github/workflows/ci.yml
```

## 5. Data and contracts

### 4.1 Persistent model

- **Users, sessions, workspaces, memberships.** A user can belong to more than one workspace. A workspace member is an owner, analyst, or viewer. Persist session expiry and revocation.
- **API sources and ingestion credentials.** Each source belongs to one workspace. Store a one-way digest of a high-entropy credential, label, creation time, and revocation state. Display the raw key only once on creation or rotation. Rotation invalidates the previous key atomically.
- **Security events.** Store source ID, caller-supplied event UUID, server receipt timestamp, request timestamp, source IP, normalized route template, HTTP method, response status, optional duration in milliseconds, and explicit event type, including `request` and `login_failed`. UTC timestamps only. Derive workspace ownership from the authenticated source. Do not accept caller-supplied workspace IDs.
- **Detector jobs.** Insert the event and its processing job in the same DB transaction. Enforce uniqueness of `(source_id, event_uuid)`. A retry of a previously accepted event must not create a second event or job.
- **Alerts, evidence, comments, history.** Persist workspace and source, rule key, severity, source IP, interval and count at first trigger, rule threshold and window snapshot, status, optional assignee, timestamps, comment authors/text, and status/assignment changes. Ensure evidence cannot cross workspace or source boundaries. Use foreign keys and uniqueness constraints. Index event lookup by source, IP and receipt time, and list queries by workspace and relevant filter/time fields. Use bounded pagination and a stable sort with an ID tie-breaker.

### 4.2 Public and internal interfaces

Use the paths below as the canonical contract unless an existing API already covers them. If adapting paths, document the equivalents and align the frontend, README, demo, and tests. Use UUID identifiers, UTC ISO 8601 values, consistent status codes, and DTOs that never expose secrets.

| Surface | Required operations |
|---|---|
| Core auth | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Core workspaces | List/create workspaces, list members, owner-managed addition of an existing account by email with assigned analyst/viewer role |
| Core sources | List/create sources, rotate and revoke keys in the selected workspace |
| Core monitoring | List/filter events, retrieve dashboard statistics, list/filter alerts, retrieve alert detail and evidence |
| Core investigation | Update status/assignee, add a comment, read history |
| Ingestion | `POST /ingest/v1/events`, source credential required; new event returns 202, identical retry returns 200, same UUID with different validated content returns 409 |
| Health | `GET /health/live` and `GET /health/ready` on Core and Ingest, plus a detector heartbeat timestamp persisted for the smoke script. Expose no internal DB or job details. |

Limit input size before parsing at the proxy and service boundary. Validate allowed methods, status codes, lengths, timezone-aware timestamps, recognized event types, valid IPs, and nonnegative duration. Store only an explicitly allowed set of metadata. Reject query strings and fragments in route templates. Never store request/response bodies, Authorization or Cookie headers, raw passwords, or tokens. Use the template from the instrumented router rather than arbitrary raw URL paths.

## 6. Authentication and permissions

- Use Argon2id for password hashing. Use opaque high-entropy server-side sessions with only token digests persisted. Send session cookies as HttpOnly and SameSite, with Secure enabled in the HTTPS production configuration. Apply expiry, revoke on logout, and enforce CSRF protection for state-changing browser routes, including a same-origin check and an appropriate CSRF mechanism. Keep the frontend and Core API on one origin in the deployed app. Use a local-only dev configuration for HTTP.
- Deny access by default. Owners manage members and sources and can investigate. Analysts can see logs and investigate. Viewers can read workspace data but cannot comment, assign, change status, or manage settings. Only assign an alert to an owner or analyst in that same workspace. A logged-in user outside a workspace cannot act on its IDs. Use 401 for missing sessions, 403 for disallowed roles within a workspace, and 404 for inaccessible foreign objects. Apply identical scoping to metrics, event evidence, comments, and history.
- Add login and ingestion limits with a documented configuration and tests. Do not trust unsolicited forwarding headers. The `source_ip` in an event is telemetry supplied by its authenticated source, not proof of identity or an authorization input.
- Parameterize database operations, render comments as plain text, keep secrets out of logs and git, use environment configuration, and disable demo credentials/features in production. Seed only isolated demo/test databases. Document handling of stored IP metadata and how an operator can remove old events without orphaning alert evidence.

## 7. Detection and reliability

Default rules for the classroom demo:

| Rule key | Counted events | Threshold | Window | Default severity |
|---|---|---:|---:|---|
| `failed_login_burst` | Explicit `login_failed` events indicating sign-in failure | 5 | 2 minutes | High |
| `high_request_volume` | All validated request events, including login events | 101 | 1 minute | Medium |
| `repeated_access_denial` | HTTP 401 or 403 outside the explicit failed-login stream | 10 | 5 minutes | Medium |

Count separately per source ID and source IP. Use trusted server receipt timestamps for decisions and preserve client timestamps for evidence. Define the counting interval as `(t - window, t]`, with `t` the receipt time of the event being evaluated. Use the same stable order in the worker and event query. For equal receipt timestamps, use a unique ingestion sequence and do not count rows later than the current sequence at that timestamp. Detect crossings by comparing the count in the current window before and after including the current qualifying event. Document that this makes delayed batches reflect their arrival rate, not the original historical traffic rate. Do not use IP alone as proof that an alert is a confirmed incident.

Process pending jobs in stable receipt order using a single worker for the MVP. Compute a rule only if its trigger event qualifies. Acquire each job and record the rule decision, any alert/evidence, and job completion in one DB transaction. Make writes idempotent with a unique trigger-event key for each rule, unique alert/evidence links, and a DB-side guard or locking when creating alerts for the same rule/source/IP. Create an alert on a transition from below threshold to at/above threshold, then suppress further alerts for the same rule/source/IP for one window from its trigger. A crossing during suppression is not queued for later delivery. After suppression, a new alert requires a fresh crossing. Subsequent events must not overwrite frozen trigger evidence. Human resolution is independent of detection and should not reset suppression. Do not assume worker replicas are safe unless you implement and test ordering and concurrent processing.

On a transient failure, roll back the processing transaction, keep the job pending, and retry with bounded backoff. After bounded failures, record a sanitized failure state and document a manual recovery command that requeues a failed job without duplicating alerts. Test the worker down/up path and verify no accepted event disappears across a container restart. An ingestion response confirms persistence, not that analysis has already run.

## 8. Frontend workflows

- **Sign in and setup.** Registration, login, logout, workspace selector, source setup, one-time key display, and a helpful empty workspace state.
- **Overview.** Total requests, failed logins, access denials, and open alerts for the selected source/time range. Show a traffic chart with a time range selector and fixed, documented bucket granularity. Use real aggregates from PostgreSQL, with zero-filled time buckets. Do not count alerts as requests or sum overlapping alert evidence as unique suspicious requests.
- **Event explorer.** Filter by time range, source, IP, route, method, and status. Provide pagination, filter reset, clear empty/error states, and deterministic results.
- **Alerts.** Filter by status/severity/source. Show why the alert fired, with the rule condition, actual count, time window, source/IP, and linked evidence. Support `New → Investigating → Resolved` and `New/Investigating → False positive`. Terminal statuses are read-only for status transitions in the MVP. Record assignment and status changes with actor and timestamp. Allow workspace investigators to comment, and show persisted comments and history after reload or in a separate member's session.
- **Usability.** Keep loading, error and empty states distinct. Use keyboard-accessible controls and labels, legible responsive layout, and status text in addition to color. Show a manual refresh and poll dashboard/alerts at a documented interval. Keep browser feedback honest when an update fails.

## 9. Demo data and repeatable walkthrough

Normal integration: run a separate local Demo API and have its middleware emit whitelisted request metadata from ordinary requests (for example, browsing demo products or a successful sign-in with one known test account). Prove at least one genuine Demo API request traverses ingestion and appears in Event Explorer.

Detection demo: generate **synthetic event records**, not suspicious HTTP traffic against the monitored API. Submit the records through the local test ingestion endpoint, with deterministic event IDs or reproducible seed data, timestamps controlled by the test fixture when needed, and reserved documentation IP ranges. Seed normal activity, three independent threshold-crossing scenarios, an under-threshold control for each rule, and an ordinary occasional access denial. Keep scenarios isolated by source or IP so the expected alert for each is unambiguous. Run data generators only against the configured local/isolated Compose test environment. Do not generate credential guesses, high-volume requests to a target API, or use real customer logs.

Document a demo that another student can reproduce: start stack → sign in → select workspace and source → confirm ordinary event → load synthetic scenarios → see three rule types in alerts → inspect one alert's evidence → assign it → comment from a second member's session → resolve → reload and verify history. Make demo seeding rerunnable with predictable results, without deleting unrelated database contents. Do not rely on sleeping for full detection windows in automated tests. Use a controlled clock in unit and integration tests and condition-based polling with timeouts in browser tests. Browser fixtures may use the real receipt clock with an ingestion limit configured for the isolated demo so fixtures reach the intended rule counts without overriding production limits.

## 10. Build order and self-fix loop

1. **Baseline:** inspect repo, dependencies, Docker and git. Establish config, service health, database migration and a minimal working stack.
2. **Functional vertical slice:** authenticate, create workspace/source, record a Demo API event in PostgreSQL, and show it in Event Explorer. Verify locally before adding all screens.
3. **Detection:** implement all three rules, durable job processing, evidence and alert APIs. Verify below threshold, boundary, matching alert, dedupe, and restart.
4. **Collaboration and dashboards:** finish roles, dashboard queries, filters, shared alert details, assignment, comments, and history. Test independently with two member accounts and a nonmember.
5. **Release verification:** run a clean local smoke test with isolated volumes, migrate an empty test DB, run all automated checks, and complete the browser demo. Finish README, CI and cloud runbook.

After each milestone, run the narrow relevant checks and then affected integration tests. If something fails, keep a short record in the form `check → failure evidence → root cause → fix → rerun outcome`.

1. Reproduce it using the smallest real workflow or failing test. Read the actual exit code, service logs, migration output, or browser trace. Distinguish a product bug from an environment problem.
2. Add or refine a regression test for the intended behavior when practical. Make the smallest root-cause fix.
3. Run the exact failing check again and then related suites. If the same failure persists, revisit the hypothesis. Do not repeat unchanged commands indefinitely.
4. Do not weaken the requirement, bypass authentication, delete assertions, suppress checks, or swap in fake responses to make tests green. Never mark unrun checks as passed.
5. If an external dependency blocks a check, keep completing independent work. Record the blocked command/action, observed reason, what did pass, and the precise input or action needed to resume. Do not run destructive git commands, erase volumes containing user data, push, or publish to cloud without the user's authorization for that action.

Use bounded waits and cleanup test resources after verification. Make the project runnable from macOS Terminal, Windows PowerShell and Linux. If extra helper scripts are required, supply documented commands that work on Windows, such as Compose or Python entry points. Document expected URLs, environment setup and common startup failures.

## 11. Code style and Git workflow

**Python:** Type public service functions, use `snake_case`, keep FastAPI routes thin, validate at the boundary, and keep explicit transactions in service or repository functions. Avoid broad exception swallowing. Use Ruff formatting and pytest. Inject a clock or pass timestamps into the rule logic so tests do not depend on wall time.

Example of the window convention and a focused regression test. Match existing module names and import locations.

```python
from datetime import UTC, datetime, timedelta


def in_detection_window(
    received_at: datetime, as_of: datetime, window: timedelta
) -> bool:
    return as_of - window < received_at <= as_of


def test_detection_window_excludes_start_and_includes_end() -> None:
    as_of = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    window = timedelta(minutes=2)

    assert not in_detection_window(as_of - window, as_of, window)
    assert in_detection_window(as_of, as_of, window)
```

**TypeScript:** Use strict mode, `PascalCase` for components, `camelCase` for functions, and explicit API contract types. Centralize the HTTP client instead of hard-coding hosts in components. Map network or HTTP failures to a displayed error state. Do not introduce `any` or suppress errors to get a clean build.

```ts
export type AlertStatus = "new" | "investigating" | "resolved" | "false_positive";

export function isOpen(status: AlertStatus): boolean {
  return status === "new" || status === "investigating";
}
```

**Git:** Inspect the existing diff before editing, separate changes by concern, and run `git diff --check` before handoff. Review your diff for inconsistent contracts, accidental changes, secrets, unrelated formatting, and generated files. Commit only when requested and use a focused message such as `feat(detector): persist threshold-crossing alerts`. Do not stage unrelated changes. Never edit dependency or build output directories by hand. Use lockfiles and forward migrations instead of patching installed dependencies or rewriting applied migrations.

## 12. Working boundaries

| Level | Instructions |
|---|---|
| Always | Work locally on the requested product. Preserve user changes. Implement and run relevant tests. Keep authorization enforced server-side. Use fake data and isolated test resources. Add forward-only migrations when data changes. |
| Ask first | Get authorization before pushing, publishing or deploying to a remote environment, changing remotes, running a migration against non-test data, or deleting existing data/volumes. Continue local implementation and verification while an external step is pending. |
| Never | Commit secrets, print credentials, alter or export real logs for the demo, generate offensive traffic, disable permissions or tests just to pass, use destructive git commands, or edit generated/vendor directories to hide failures. |

## 13. Definition of Done

Record commands and actual outcomes in `docs/implementation-status.md`. Start each entry with `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`, then give the command, observed evidence and next action when relevant. A required check marked not run or blocked means the release is not fully verified.

| Gate | Evidence required |
|---|---|
| Clean startup | Documented Compose setup starts from an empty test database; Alembic upgrades to head; services become ready; frontend build succeeds |
| Authentication / authorization | Registration, login and logout work; negative session, workspace and role cases pass; revoked/rotated ingestion keys behave correctly |
| Ingestion | Ordinary Demo API request persists and is visible in browser; valid event, invalid data, identical duplicate and conflicting duplicate all tested |
| Detection | All three rules pass threshold-minus-one, exact threshold, window boundary and source/IP separation tests; worker retry/restart and alert dedupe integration tests pass |
| Investigation | Browser E2E proves real evidence, filtering, two-member collaboration, assignment, status change, persisted comments and history; nonmember cannot access the data |
| Quality | Python lint/tests, TypeScript typecheck/lint, frontend unit tests/build and Playwright all pass locally or in actual CI; no required test silently skipped |
| Reproducibility | README includes exact start, setup, demo and verification commands; migration, demo fixtures, architecture explanation and CI definitions exist as versionable files in the working tree, with no secrets |
| Cloud release | Deployment guide describes HTTPS, environment variables, managed/persistent DB, migrations, health and smoke checks. Claim “deployed online” only after an authorized deployment and verification of the live URL. If no hosting access is authorized, deliver and verify locally, and report cloud deployment as a separate pending step. |

When finished, summarize what works, exact startup/verification commands, actual test results, known limitations, and whether the app is local-only or live. Point to the main docs. Do not say “bug-free.” State what you verified.

## Reference for this guide

The instruction structure is adapted from [GitHub’s guide to writing agent instructions](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/). This root file is a repository-wide brief for Cursor, not a GitHub Copilot persona file.
