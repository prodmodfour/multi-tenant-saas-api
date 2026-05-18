# Operations guide

This guide covers local operation for the portfolio/demo API and highlights the
production work that would be required before running a real SaaS system.

## Local prerequisites

- Python 3.12
- `uv`
- Docker and Docker Compose for the optional local stack
- A PostgreSQL database when running the API outside Compose

Install dependencies and run tests:

```bash
uv sync --all-groups
uv run pytest
```

Run the full quality gate before committing changes:

```bash
scripts/quality-gate.sh
```

The quality gate runs shell syntax checks, dependency sync, Ruff, Ruff format
check, mypy strict checks, pytest with coverage, Docker Compose config
validation, and automation guardrails.

## Configuration

Application settings use the `SAAS_API_` prefix. Common settings are documented
in `README.md` and `example.env`.

Important operational defaults:

- `SAAS_API_DOCS_ENABLED=false` disables OpenAPI docs unless explicitly enabled.
- `SAAS_API_DATABASE_URL` must point to an async PostgreSQL URL.
- `SAAS_API_JWT_SECRET` defaults to a local placeholder and must be replaced in
  real deployments.
- `SAAS_API_PASSWORD_MIN_LENGTH` controls the local demo password policy.

Keep local `.env` files untracked. Do not commit real secrets, database URLs,
private hostnames, or credentials.

## Running with Docker Compose

Start the local stack:

```bash
docker compose up --build
```

Services:

| Service | Purpose | Local URL |
| --- | --- | --- |
| `api` | FastAPI app with migrations run before startup. | <http://localhost:8000> |
| `postgres` | Local PostgreSQL with placeholder credentials. | `localhost:5432` |
| `prometheus` | Scrapes API metrics. | <http://localhost:9090> |
| `grafana` | Local dashboard with provisioned datasource. | <http://localhost:3000> |

Useful endpoints:

- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz>
- Readiness: <http://localhost:8000/readyz>
- Metrics: <http://localhost:8000/metrics>
- Prometheus targets: <http://localhost:9090/targets>
- Grafana dashboard: **Dashboards** → **Portfolio SaaS API** →
  **Multi-Tenant SaaS API Overview**

Stop the stack:

```bash
docker compose down
```

Remove local volumes only when intentionally discarding local demo data:

```bash
docker compose down --volumes
```

## Running outside Docker Compose

1. Ensure PostgreSQL is available.
2. Configure `SAAS_API_DATABASE_URL` with a local placeholder or a safe local
   value.
3. Apply migrations.
4. Start Uvicorn.

```bash
uv run alembic upgrade head
uv run uvicorn multi_tenant_saas_api.main:app --reload
```

OpenAPI remains disabled unless `SAAS_API_DOCS_ENABLED=true` is set.

## Database migrations

Alembic owns schema changes. The initial migration creates users,
organisations, memberships, projects, API keys, audit events, and idempotency
records with tenant-oriented indexes.

Local migration command:

```bash
uv run alembic upgrade head
```

Production migration hardening should include backup/restore validation,
backward-compatible rollout planning, deploy ordering, lock-time review, and a
rollback strategy.

## Health and readiness

`GET /healthz` is a lightweight liveness endpoint. It returns application name,
version, environment, and `status: "ok"` without checking external dependencies.

`GET /readyz` checks PostgreSQL with a minimal round trip. It returns:

- `200` and `status: "ready"` when dependencies are available;
- `503` and `status: "not_ready"` when the database is unavailable.

Readiness responses identify the dependency name and a safe status without
exposing database credentials or driver exception details.

## Metrics and dashboards

`GET /metrics` exposes Prometheus text metrics from an app-local registry.
Important metric families include:

- `saas_api_requests_total`
- `saas_api_request_duration_seconds`
- `saas_api_auth_attempts_total`
- `saas_api_organisations_created_total`
- `saas_api_projects_created_total`
- `saas_api_api_keys_created_total`
- `saas_api_api_keys_revoked_total`
- `saas_api_audit_events_recorded_total`
- `saas_api_idempotency_replays_total`
- `saas_api_idempotency_conflicts_total`

Prometheus scrapes `api:8000/metrics` inside the Compose network. Grafana loads a
basic dashboard from `observability/grafana/dashboards/saas-api-overview.json`.

Production observability should add authentication or network controls for
metrics, alert rules, retention planning, log aggregation, traces, and SLOs.

## Logging and request IDs

The app emits structured JSON logs. The request middleware propagates an incoming
`X-Request-ID` header or generates one when absent. Responses include the
resolved request ID.

Operational practices:

- Use request IDs to correlate client reports with server logs.
- Never place passwords, bearer tokens, raw API keys, or key hashes in logs.
- Avoid high-cardinality labels or tenant-specific values in metrics.

## CI and quality gates

GitHub Actions CI runs on pull requests and pushes. It uses Python 3.12, uv, and
a PostgreSQL service container, then runs the same broad checks as the local
quality gate plus an Alembic migration upgrade against PostgreSQL.

Automation guardrails are intentionally conservative. If a guardrail fails,
inspect the reported file and line, then either remove the risky content or
replace it with an obvious placeholder.

## Data retention and backup posture

The local Compose stack stores PostgreSQL, Prometheus, and Grafana data in Docker
volumes. These volumes are disposable demo state and are not backed up.

A production system would need:

- database backups with restore drills;
- point-in-time recovery requirements;
- audit log retention and access policy;
- idempotency record retention/cleanup policy;
- metrics and log retention policies;
- disaster recovery objectives and runbooks.

## Deployment considerations

This project does not include a production deployment target. Before deploying a
real service, review:

- container image provenance and vulnerability scanning;
- non-root runtime user and file permissions;
- secret injection through managed secret storage;
- TLS, network policy, and ingress controls;
- migration and release ordering;
- horizontal scaling and database connection pool sizing;
- rate limiting and abuse controls;
- alerting and on-call procedures.

## Known operational limitations

- Docker Compose credentials and JWT settings are local placeholders only.
- API key scopes are coarse-grained and project-focused.
- Idempotency cleanup is not implemented.
- There is no background worker system.
- There is no production backup, alerting, tracing, or deployment automation.
- Local auth is intentionally minimal and should not be treated as a hardened
  identity platform.
