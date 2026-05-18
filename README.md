![CI](https://github.com/prodmodfour/multi-tenant-saas-api/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-multi--tenant-blue)
![RBAC](https://img.shields.io/badge/RBAC-tenant%20isolation-purple)
# Multi-Tenant SaaS API

**Production-style FastAPI backend portfolio project for a multi-tenant SaaS API.**

This repository is an independent public portfolio project. It is designed to show practical
backend/platform engineering judgement: tenant isolation, RBAC, PostgreSQL persistence,
Alembic migrations, secure credential handling patterns, audit logging, idempotency,
observability, Docker Compose local infrastructure, CI, tests, runbooks, and ADRs.

## Suggested review path for hiring reviewers

If you have limited time, review in this order:

1. Start with this README for scope, boundaries, quick start, and the API surface.
2. Skim [docs/architecture.md](docs/architecture.md) for the layer boundaries and tenant model.
3. Skim [docs/security.md](docs/security.md) for auth, API key, audit, and production-hardening notes.
4. Run `scripts/quality-gate.sh` to see linting, type checks, tests, Docker Compose validation, and guardrails.
5. Run the local stack plus `scripts/smoke-demo.sh` to exercise a safe end-to-end demo.
6. Inspect representative tests such as `tests/test_projects_api.py`, `tests/test_api_keys_api.py`,
   `tests/test_idempotency_api.py`, and `tests/test_guardrails.py`.

## Public-safety constraints

This project is intentionally generic and public-safe:

- No employer code, private data, internal hostnames, credentials, screenshots, or non-public architecture.
- Demo users, configuration values, Grafana credentials, JWT settings, and database passwords are local placeholders only.
- The repository should not imply employer endorsement or contain organisation-specific implementation details.
- If you add local private terms for scanning, keep them outside git and point
  `SAAS_API_FORBIDDEN_TERMS_FILE` at that untracked file.

## Security boundaries

This is a portfolio implementation, not a production identity or security baseline.
It models good hygiene while remaining intentionally small enough to review:

- Passwords are hashed before persistence; password hashes are never returned by API responses.
- API keys are stored as deterministic hashes plus non-secret prefixes; raw API key material is returned only by the intentional one-time create response.
- Bearer tokens, raw API keys, passwords, password hashes, and key hashes must not be logged or stored in audit metadata.
- OpenAPI docs are disabled by default and enabled only when `SAAS_API_DOCS_ENABLED=true`.
- Production deployments would need managed secrets, TLS, hardened identity, token/key rotation, alerting, backups, rate limiting, and operational review.

## Implemented scope

| Area | Implemented |
| --- | --- |
| API framework | FastAPI app factory, route modules, Pydantic request/response schemas, docs toggle. |
| Persistence | Async SQLAlchemy, PostgreSQL models, repository layer, Alembic initial migration. |
| Tenancy | Organisations as tenant roots, organisation memberships, tenant-scoped repositories and service checks. |
| Auth | Local demo email/password registration, login, short-lived bearer access tokens, `GET /me`. |
| RBAC | `owner`, `admin`, `member`, and `viewer` roles with last-owner protection. |
| Projects | Tenant-scoped create/read/update/soft-delete with pagination, filtering, and sorting. |
| API keys | Organisation-scoped API key management and API key authentication for project endpoints. |
| Audit | Append-only audit service and tenant-scoped audit log API. |
| Idempotency | Optional `Idempotency-Key` support for selected unsafe creation endpoints. |
| Observability | Structured JSON logging, `X-Request-ID`, health/readiness, Prometheus metrics, local Grafana dashboard. |
| Automation | Quality gate, public-safety/architecture/secret-response guardrails, GitHub Actions CI. |
| Local demo | Dockerfile, Docker Compose stack, Prometheus/Grafana config, and `scripts/smoke-demo.sh`. |
| Documentation | Architecture, security, API walkthrough, operations, runbook, and ADRs. |

## Out of scope

The project deliberately does not implement:

- OAuth, SSO, MFA, email verification, password reset emails, refresh-token rotation, or full identity-provider workflows.
- Billing, subscriptions, webhooks, background job processing, or multi-region deployment automation.
- Fine-grained API key scopes beyond project endpoint access.
- Production secret management, TLS termination, rate limiting, alert rules, backups, or disaster recovery automation.
- Arbitrary command execution, subprocess execution from user input, user-supplied plugin execution, or hidden bypass users.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Docker and Docker Compose for the optional local API/PostgreSQL/Prometheus/Grafana stack

## Quick start

Install dependencies and run the test suite:

```bash
uv sync --all-groups
uv run pytest
```

Run the full local quality gate:

```bash
scripts/quality-gate.sh
```

Common shortcuts are available through `make`:

```bash
make install
make lint
make test
make quality
```

Start the local demo stack:

```bash
docker compose up --build
```

Useful local URLs when Compose is running:

- API: <http://localhost:8000>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz>
- Readiness: <http://localhost:8000/readyz>
- Metrics: <http://localhost:8000/metrics>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000> (`admin` / `local-placeholder-grafana-password`)

After `/readyz` reports ready, run the safe smoke demo:

```bash
scripts/smoke-demo.sh
```

The smoke demo registers placeholder `example.com` users, logs in, creates an organisation,
adds a member, creates/lists/updates a project, creates and uses an API key on a project
endpoint, revokes the API key, reads audit events, and checks metrics. It captures bearer
tokens and the one-time API key response in memory only and does not print them.

Optional smoke-demo overrides:

```bash
SAAS_API_DEMO_BASE_URL=http://localhost:8000 scripts/smoke-demo.sh
SAAS_API_DEMO_RUN_ID=example-review scripts/smoke-demo.sh
```

Shut down the stack with:

```bash
docker compose down
```

Add `--volumes` only when you intentionally want to delete local PostgreSQL, Prometheus,
and Grafana data volumes.

## Configuration

Configuration uses environment variables prefixed with `SAAS_API_`. See `example.env` for
public-safe local placeholders.

| Variable | Default | Description |
| --- | --- | --- |
| `SAAS_API_APP_NAME` | `multi-tenant-saas-api` | Application name used in FastAPI metadata and health responses. |
| `SAAS_API_APP_VERSION` | `0.1.0` | Application version used in FastAPI metadata and health responses. |
| `SAAS_API_ENVIRONMENT` | `local` | Environment label included in health responses and logs. |
| `SAAS_API_LOG_LEVEL` | `INFO` | Structured JSON logging level. |
| `SAAS_API_DOCS_ENABLED` | `false` | Enables `/docs`, `/redoc`, and `/openapi.json` for local exploration when set to `true`. |
| `SAAS_API_DATABASE_URL` | `postgresql+asyncpg://saas_api:saas_api@localhost:5432/saas_api` | Async SQLAlchemy PostgreSQL URL. The default is a local placeholder only. |
| `SAAS_API_JWT_SECRET` | `local-placeholder-jwt-secret-not-for-production` | Local placeholder signing secret for demo bearer tokens. Production requires managed secrets and rotation. |
| `SAAS_API_JWT_ISSUER` | `multi-tenant-saas-api-local` | Issuer claim used when creating and validating bearer access tokens. |
| `SAAS_API_ACCESS_TOKEN_TTL_SECONDS` | `900` | Lifetime for local demo bearer access tokens. |
| `SAAS_API_PASSWORD_MIN_LENGTH` | `12` | Minimum password length enforced before password hashing. |

Do not copy real credentials into committed files. If you create a local `.env`, keep it untracked.

## API surface

System endpoints:

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`

Auth endpoints:

- `POST /auth/register`
- `POST /auth/login`
- `GET /me`

Organisation endpoints:

- `POST /orgs`
- `GET /orgs`
- `GET /orgs/{organisation_id}`
- `PATCH /orgs/{organisation_id}`

Membership endpoints:

- `GET /orgs/{organisation_id}/members`
- `POST /orgs/{organisation_id}/members`
- `PATCH /orgs/{organisation_id}/members/{user_id}`
- `DELETE /orgs/{organisation_id}/members/{user_id}`

Project endpoints:

- `POST /orgs/{organisation_id}/projects`
- `GET /orgs/{organisation_id}/projects?limit=50&offset=0&status=active&name=demo&sort_by=created_at&sort_direction=desc`
- `GET /orgs/{organisation_id}/projects/{project_id}`
- `PATCH /orgs/{organisation_id}/projects/{project_id}`
- `DELETE /orgs/{organisation_id}/projects/{project_id}`

API key endpoints:

- `POST /orgs/{organisation_id}/api-keys`
- `GET /orgs/{organisation_id}/api-keys`
- `DELETE /orgs/{organisation_id}/api-keys/{api_key_id}`

Audit endpoint:

- `GET /orgs/{organisation_id}/audit-events`

## Auth and RBAC summary

Local demo authentication supports email/password registration and login. Registration stores
only an Argon2id-derived password hash. Login returns a short-lived bearer access token for
user endpoints. `GET /me` returns the current public user plus organisation memberships.

Organisations are the tenant boundary. User-driven business workflows resolve the current
principal, load the user's membership for the target organisation, and check permissions before
reading or mutating tenant-owned data.

| Role | Summary |
| --- | --- |
| `owner` | Manage organisation, members, API keys, projects, and audit events. |
| `admin` | Manage metadata, non-owner members, API keys, projects, and audit events; cannot grant/change/remove owners. |
| `member` | Read organisation metadata and read/write projects. |
| `viewer` | Read organisation metadata and projects only. |

Every organisation must retain at least one owner. Last-owner removal and downgrade attempts
are rejected. Cross-tenant access is denied before tenant-owned rows are listed or mutated.

## API key summary

Owner/admin users can create, list, and revoke organisation API keys. The create response
returns `raw_key` exactly once; later list/revoke responses expose metadata only. The database
persists only key hashes and short non-secret prefixes for identification.

API keys authenticate with `Authorization: Bearer <raw-api-key>` on project endpoints only.
They are scoped to exactly one organisation, cannot access other tenants, cannot manage
members, cannot read audit logs, and cannot create/list/revoke other API keys. Revoked keys
are denied during authentication.

## Audit and idempotency summary

Core business workflows create append-only audit events for registration/login, organisation
create/update, member add/update/remove, project create/update/delete, and API key create/revoke.
Audit metadata is intentionally small and rejects obvious secret-bearing field names.
Only owner/admin members can read tenant-scoped audit events.

Optional `Idempotency-Key` support is implemented for:

- `POST /orgs`
- `POST /orgs/{organisation_id}/projects`
- `POST /orgs/{organisation_id}/api-keys`

A replay with the same principal, method, path, organisation scope, idempotency key, and body
hash returns the stored response with `Idempotency-Replayed: true`. Reusing the key with a
different request body returns `409 Conflict` without exposing request hashes. API key creation
replays intentionally omit raw API key material.

## Observability

The API provides:

- Structured JSON logs with request-scoped `X-Request-ID` propagation.
- `GET /healthz` for liveness without dependency checks.
- `GET /readyz` for PostgreSQL readiness through a minimal `SELECT 1` check.
- `GET /metrics` for Prometheus text exposition using low-cardinality route-template labels.

Implemented metric families:

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

The Docker Compose stack includes Prometheus and Grafana with repository-owned provisioning:

- Prometheus config: `observability/prometheus/prometheus.yml`
- Grafana datasource provisioning: `observability/grafana/provisioning/datasources/prometheus.yml`
- Grafana dashboard provisioning: `observability/grafana/provisioning/dashboards/dashboards.yml`
- Grafana dashboard JSON: `observability/grafana/dashboards/saas-api-overview.json`

## Testing and quality gates

The repository uses Ruff, mypy strict mode, pytest, pytest-cov, shell syntax checks, Docker
Compose config validation, Alembic migration checks in CI, and custom automation guardrails.

Run everything locally with:

```bash
scripts/quality-gate.sh
```

The gate runs:

- shell syntax checks for scripts
- `uv sync --locked --all-groups` when `uv.lock` is present
- Ruff lint and format checks
- mypy over `src` and `tests`
- pytest with coverage
- Docker Compose config validation
- public-safety/private-term scanning
- route-layer architecture-boundary scanning
- response-schema secret-leakage scanning

GitHub Actions CI is defined in `.github/workflows/ci.yml` and mirrors the quality gate while
also running Alembic migrations against a PostgreSQL service container.

## Architecture links

The implementation follows the project layer rule:

```text
routes -> schemas -> services -> repositories -> database
```

Routes are thin HTTP adapters. Schemas validate API input/output. Services own business
workflows, RBAC, tenant checks, idempotency integration, and audit integration. Repositories
own SQLAlchemy access. Route functions must not issue SQLAlchemy queries or hash credentials.

Detailed documentation:

- [Architecture](docs/architecture.md)
- [Security model](docs/security.md)
- [API walkthrough](docs/api-walkthrough.md)
- [Operations guide](docs/operations.md)
- [Runbook](docs/runbook.md)

Architecture decision records:

- [0001 — Organisations as tenants](docs/decisions/0001-organisations-as-tenants.md)
- [0002 — Role-based access control](docs/decisions/0002-role-based-access-control.md)
- [0003 — Hashed passwords and API keys](docs/decisions/0003-hashed-passwords-and-api-keys.md)
- [0004 — Idempotency records](docs/decisions/0004-idempotency-records.md)
- [0005 — Append-only audit events](docs/decisions/0005-append-only-audit-events.md)

## Limitations

- Local authentication is intentionally simple and is not a hardened identity platform.
- JWT and database values in `example.env` and `docker-compose.yml` are public-safe local placeholders only.
- API key access is coarse-grained to project endpoints rather than per-action scopes.
- Idempotency cleanup and high-concurrency duplicate-key hardening are intentionally minimal for portfolio scope.
- Observability is local-demo oriented; production alerting, retention, authentication, and dashboard hardening are not included.
- The smoke demo exercises the happy path; RBAC denial, tenant isolation, idempotency conflict, and secret-leakage cases live in pytest coverage.
- Production deployment would require reviewed infrastructure, TLS, managed secrets, backups, rate limiting, and incident response processes.
