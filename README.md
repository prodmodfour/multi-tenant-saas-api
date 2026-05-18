# Multi-Tenant SaaS API

`multi-tenant-saas-api` is an independent public portfolio project that will grow into a production-style FastAPI backend for a multi-tenant SaaS product.

The project is intentionally generic and public-safe. It is not based on employer code, private systems, internal URLs, credentials, screenshots, or non-public architecture.

## Portfolio goals

This repository is designed to demonstrate commercial backend/platform engineering skills, including:

- FastAPI API design
- PostgreSQL persistence and migrations
- multi-tenant data modelling and tenant isolation
- authentication and role-based access control
- organisation membership management
- hashed password and API key storage
- audit logging and idempotency keys
- pagination, filtering, and sorting
- structured JSON logging and request ID propagation
- health/readiness checks and Prometheus metrics
- Docker Compose local infrastructure
- GitHub Actions CI, tests, documentation, runbooks, and ADRs

## Security and public-safety boundaries

This is a portfolio implementation, not a production identity or security baseline.

- Do not commit real secrets, credentials, private data, or employer-specific material.
- Use only local placeholder values in examples and local development files.
- Production deployments would require real secret management, TLS, hardened authentication, alerting, backups, and operational review.
- Password hashing utilities store only derived hashes; API key workflows store only key hashes plus non-secret identification prefixes.
- Raw API key material is returned only by the intentional one-time create response.

## Current status

The project currently includes the repository skeleton, FastAPI application shell, persistence layer contracts, and the first tenant-scoped API workflows:

- Python 3.12 package using a `src/` layout
- Hatchling build backend
- Ruff, mypy strict mode, pytest, and pytest-cov configuration
- quality gate script
- GitHub Actions CI workflow for dependency sync, linting, formatting, type checks, migrations, tests, and Docker Compose validation
- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix
- structured JSON logging with request ID context
- `X-Request-ID` propagation
- `GET /healthz` liveness endpoint
- `GET /readyz` readiness endpoint with a PostgreSQL `SELECT 1` dependency check
- `GET /metrics` Prometheus text exposition endpoint
- domain identifiers, organisation roles, permission mapping, project statuses, and audit actions
- Pydantic request/response schemas for the planned auth, organisation, membership, project, API key, audit, and pagination contracts
- async SQLAlchemy engine/session helpers
- SQLAlchemy models for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- Alembic configuration and an initial PostgreSQL migration
- repository classes for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- tenant-scoped repository methods for organisation membership lists, project access, API key management, audit event reads, and idempotency lookups
- RBAC and tenant-context services for current-principal resolution, membership lookup, permission checks, and last-owner protection
- password policy checks plus Argon2id password hashing and verification utilities
- signed bearer access token creation/validation utilities and a typed authenticated principal model
- request-scoped database session dependency wiring for API workflows
- auth service workflows and routes for registration, login, and current-user lookup
- organisation service workflows and routes for tenant creation, membership-scoped listing, detail reads, and owner/admin metadata updates
- membership management service workflows and routes for owner/admin member listing, member add, role update, removal, admin owner-operation restrictions, and last-owner protection
- project service workflows and routes for tenant-scoped create/read/update/soft-delete operations, pagination, status/name filtering, created_at/name/status sorting, viewer read-only user access, and organisation-scoped API key access
- API key management workflows and routes for owner/admin key creation, metadata listing, revocation, hashed storage, one-time raw key creation responses, and revoked-key authentication denial
- `POST /auth/register`, `POST /auth/login`, `GET /me`, `POST /orgs`, `GET /orgs`, `GET /orgs/{org_id}`, `PATCH /orgs/{org_id}`, `GET /orgs/{org_id}/members`, `POST /orgs/{org_id}/members`, `PATCH /orgs/{org_id}/members/{user_id}`, `DELETE /orgs/{org_id}/members/{user_id}`, `POST /orgs/{org_id}/projects`, `GET /orgs/{org_id}/projects`, `GET /orgs/{org_id}/projects/{project_id}`, `PATCH /orgs/{org_id}/projects/{project_id}`, `DELETE /orgs/{org_id}/projects/{project_id}`, `POST /orgs/{org_id}/api-keys`, `GET /orgs/{org_id}/api-keys`, `DELETE /orgs/{org_id}/api-keys/{api_key_id}`, and `GET /orgs/{org_id}/audit-events`
- successful registration/login, organisation create/update, member add/update/remove, project create/update/delete, and API key create/revoke audit event writes through the append-only audit service with secret-safe metadata
- idempotency support for `POST /orgs`, `POST /orgs/{org_id}/projects`, and `POST /orgs/{org_id}/api-keys`, scoped by principal, method, path, request body hash, and organisation where applicable
- Prometheus metrics for HTTP requests, request duration, auth attempts, created organisations/projects/API keys, revoked API keys, audit events, and idempotency replay/conflict outcomes
- Dockerfile with a non-root runtime user and container health check
- Docker Compose stack for local API, PostgreSQL, Prometheus, and Grafana services
- local Prometheus scrape configuration for the API metrics endpoint
- Grafana provisioning for the Prometheus datasource and a basic SaaS API overview dashboard
- documentation and decisions directories

GitHub Actions CI is implemented in `.github/workflows/ci.yml`. It runs shell syntax checks, optional guardrail scripts when present, `uv sync --locked --all-groups`, Ruff, mypy, Docker Compose config validation, Alembic migration upgrade against a PostgreSQL service container, and pytest with coverage. The RBAC services are wired into the organisation, membership, project, API key, audit, idempotency-aware, and metrics APIs and remain available for future tenant-scoped routes.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) for dependency management
- Docker and Docker Compose for the optional local container stack

## Local setup

```bash
uv sync --all-groups
uv run pytest
```

Run the full local quality gate:

```bash
scripts/quality-gate.sh
```

The GitHub Actions CI workflow mirrors these checks and also runs `alembic upgrade head` against a PostgreSQL service container.

Common shortcuts are available through `make`:

```bash
make install
make lint
make test
make quality
```

## Docker Compose quick start

The local Compose stack uses public-safe placeholder configuration only. It starts the API, PostgreSQL, Prometheus, and Grafana for demo exploration:

```bash
docker compose up --build
```

The API container waits for PostgreSQL, runs `alembic upgrade head` for local demo convenience, and then starts Uvicorn. OpenAPI docs are enabled in the Compose environment for local exploration.

Useful local URLs:

- API: <http://localhost:8000>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz>
- Readiness: <http://localhost:8000/readyz>
- Metrics: <http://localhost:8000/metrics>
- Prometheus: <http://localhost:9090>
- Prometheus API target status: <http://localhost:9090/targets>
- Grafana: <http://localhost:3000> (`admin` / `local-placeholder-grafana-password`)
- Grafana dashboard: browse to **Dashboards** → **Portfolio SaaS API** → **Multi-Tenant SaaS API Overview**

Shut down the stack with:

```bash
docker compose down
```

Add `--volumes` when you intentionally want to remove local PostgreSQL, Prometheus, and Grafana data volumes.

These placeholders are not production secrets. Production deployments need managed secret storage, TLS, hardened authentication, backups, alerting, and reviewed container/runtime policies.

## Configuration

Configuration uses environment variables prefixed with `SAAS_API_`. See `example.env` for public-safe local placeholders.

| Variable | Default | Description |
| --- | --- | --- |
| `SAAS_API_APP_NAME` | `multi-tenant-saas-api` | Application name used in FastAPI metadata and health responses. |
| `SAAS_API_APP_VERSION` | `0.1.0` | Application version used in FastAPI metadata and health responses. |
| `SAAS_API_ENVIRONMENT` | `local` | Environment label included in health responses and future logs/metrics. |
| `SAAS_API_LOG_LEVEL` | `INFO` | Structured JSON logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`). |
| `SAAS_API_DOCS_ENABLED` | `false` | Enables `/docs`, `/redoc`, and `/openapi.json` for local exploration when set to `true`. |
| `SAAS_API_DATABASE_URL` | `postgresql+asyncpg://saas_api:saas_api@localhost:5432/saas_api` | Async SQLAlchemy PostgreSQL URL used by the application and Alembic migrations. The default is a local placeholder only. |
| `SAAS_API_JWT_SECRET` | `local-placeholder-jwt-secret-not-for-production` | Local placeholder signing secret for demo bearer access tokens. Production systems require managed secrets and rotation. |
| `SAAS_API_JWT_ISSUER` | `multi-tenant-saas-api-local` | Issuer claim used when creating and validating bearer access tokens. |
| `SAAS_API_ACCESS_TOKEN_TTL_SECONDS` | `900` | Lifetime for local demo bearer access tokens. |
| `SAAS_API_PASSWORD_MIN_LENGTH` | `12` | Minimum password length enforced by the password policy utility before hashing. |

OpenAPI documentation is disabled by default to model a safer production posture. Enable it only for local exploration or explicitly configured demo environments.

Do not copy real credentials into committed files. If you create a local `.env`, keep it untracked.

## Implemented API surface

System endpoints:

- `GET /healthz` — liveness check with application metadata; it does not touch external dependencies.
- `GET /readyz` — readiness check that executes a minimal PostgreSQL round trip. It returns `200` with `status: "ready"` when the database check succeeds and `503` with `status: "not_ready"` when PostgreSQL is unavailable. The failure response identifies the `postgresql` dependency without exposing database URLs, credentials, or driver exception details.
- `GET /metrics` — Prometheus text exposition for app-local metrics. The endpoint does not require authentication so local Prometheus can scrape it.

Auth endpoints:

- `POST /auth/register` — creates a local demo user, stores only an Argon2id-derived password hash, rejects duplicate email addresses, and returns public user fields.
- `POST /auth/login` — validates local email/password credentials and returns a short-lived bearer access token with generic failure behaviour for unknown email or wrong password.
- `GET /me` — requires `Authorization: Bearer <token>` and returns the current active user plus organisation membership summaries.

Password hashes and raw passwords are never returned by these endpoints. Registration and successful login create nullable-organisation audit events with empty, secret-safe metadata.

Organisation endpoints:

- `POST /orgs` — requires a bearer token, creates an organisation, derives a slug from the name when one is not supplied, enforces unique slugs, makes the creator an `owner`, records a secret-safe audit event, and supports `Idempotency-Key` replay/conflict handling scoped to the user principal.
- `GET /orgs` — requires a bearer token and returns only organisations where the current user has a membership, with `limit`/`offset` pagination metadata.
- `GET /orgs/{org_id}` — requires tenant membership and `read_organisation` permission.
- `PATCH /orgs/{org_id}` — requires tenant membership and `update_organisation` permission, so `owner` and `admin` members may update metadata while `member` and `viewer` roles are denied.

Organisation names are not globally unique; duplicate names are allowed when slugs differ. Organisation slugs are globally unique tenant identifiers.

Membership endpoints:

- `GET /orgs/{org_id}/members` — requires tenant membership and `manage_members` permission, returning paginated public member data without password hashes.
- `POST /orgs/{org_id}/members` — requires `manage_members`, adds an existing user to the organisation, rejects duplicate memberships, prevents admins from granting `owner`, and records a `member.added` audit event.
- `PATCH /orgs/{org_id}/members/{user_id}` — requires `manage_members`, changes a member role, prevents admins from changing owner memberships or granting `owner`, protects the final owner from downgrade, and records a `member.role_changed` audit event.
- `DELETE /orgs/{org_id}/members/{user_id}` — requires `manage_members`, prevents admins from removing owners, protects the final owner from removal, and records a `member.removed` audit event.

Project endpoints:

- `POST /orgs/{org_id}/projects` — requires tenant membership and `write_projects` for user access, so `owner`, `admin`, and `member` roles can create projects while `viewer` is denied. Active API keys for the same organisation can also create projects. `Idempotency-Key` replay/conflict handling is scoped to the principal, route organisation, method, path, and body hash.
- `GET /orgs/{org_id}/projects` — requires `read_projects` for user access or an active API key for the same organisation. It returns non-deleted projects scoped to that organisation only and supports `limit`, `offset`, optional `status`, optional case-insensitive `name` search, `sort_by` (`created_at`, `name`, or `status`), and `sort_direction` (`asc` or `desc`).
- `GET /orgs/{org_id}/projects/{project_id}` — requires project read access and enforces both organisation ID and project ID in the repository lookup, so project IDs from other organisations return a safe not-found response.
- `PATCH /orgs/{org_id}/projects/{project_id}` — requires project write access, updates supplied project fields, supports clearing `description` with `null`, and records a `project.updated` audit event.
- `DELETE /orgs/{org_id}/projects/{project_id}` — requires project write access, soft-deletes the project, excludes it from future default reads/lists, and records a `project.deleted` audit event.

API key endpoints:

- `POST /orgs/{org_id}/api-keys` — requires tenant membership and `manage_api_keys`, so only `owner` and `admin` members can create API keys. The initial response returns `raw_key` exactly once and persists only `key_hash` plus `key_prefix` metadata. Idempotent replays return stored key metadata plus a replay note and do not return or store raw key material.
- `GET /orgs/{org_id}/api-keys` — requires `manage_api_keys` and returns paginated metadata only; it never returns raw keys or key hashes.
- `DELETE /orgs/{org_id}/api-keys/{api_key_id}` — requires `manage_api_keys`, revokes the key, and records a secret-safe `api_key.revoked` audit event.

API keys authenticate with `Authorization: Bearer <raw_key>` on project endpoints only. They are scoped to one organisation, cannot access another tenant's projects, cannot manage members, and cannot create/list/revoke API keys. Revoked keys cannot authenticate.

Audit endpoints:

- `GET /orgs/{org_id}/audit-events` — requires tenant membership and `read_audit_events`, so only `owner` and `admin` members can read paginated audit logs. `member`, `viewer`, non-member, and cross-tenant requests are denied before audit rows are listed.

Audit events are append-only at the API/service layer. Metadata is intentionally small and secret-safe; the audit service rejects obvious secret-bearing metadata field names such as raw keys, key hashes, passwords, bearer tokens, and authorization values.

Idempotency:

- `POST /orgs`, `POST /orgs/{org_id}/projects`, and `POST /orgs/{org_id}/api-keys` accept an optional `Idempotency-Key` header.
- Reusing the same key with the same principal, method, path, organisation scope, and request body hash returns the stored response with `Idempotency-Replayed: true`.
- Reusing the same key with a different request body returns `409 Conflict` without exposing body hashes.
- API key creation replay intentionally omits `raw_key`; raw API key material is returned only by the initial create response and is never persisted in idempotency snapshots.

## Observability

The app exposes Prometheus metrics at `GET /metrics` using an app-local registry. Request metrics use low-cardinality route templates such as `/orgs/{organisation_id}/projects` instead of raw tenant IDs.

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

The Docker Compose stack includes Prometheus and Grafana containers for local exploration. Prometheus uses `observability/prometheus/prometheus.yml` to scrape the API container at `api:8000/metrics` every 15 seconds. Grafana uses provisioning files under `observability/grafana/provisioning/` to create a Prometheus datasource and load the `observability/grafana/dashboards/saas-api-overview.json` dashboard.

Local observability URLs when Compose is running:

- API metrics: <http://localhost:8000/metrics>
- Prometheus UI: <http://localhost:9090>
- Prometheus target health: <http://localhost:9090/targets>
- Grafana UI: <http://localhost:3000> (`admin` / `local-placeholder-grafana-password`)
- Grafana dashboard: **Dashboards** → **Portfolio SaaS API** → **Multi-Tenant SaaS API Overview**

These observability settings are local demo defaults only. Production deployments need authenticated dashboards, managed secrets, alerting rules, retention planning, and reviewed scrape topology.

## Role model and tenant access policy

Organisations are the tenant boundary. User-driven business workflows must resolve a current authenticated principal, load the user's membership for the target organisation, and enforce permissions before accessing tenant-owned data. Project workflows also accept active organisation-scoped API keys and require the key's organisation to match the route tenant.

| Role | Permissions |
| --- | --- |
| `owner` | Manage organisation, manage members, manage API keys, read/write projects, read audit events. |
| `admin` | Update organisation metadata, manage non-owner members, manage API keys, read/write projects, read audit events; cannot grant, change, or remove `owner` memberships. |
| `member` | Read organisation metadata and read/write projects. |
| `viewer` | Read organisation metadata and read projects only. |

The RBAC service resolves bearer tokens into secret-safe current user principals, builds tenant contexts from organisation memberships, raises explicit not-found/access-denied/permission-denied errors, and protects the invariant that an organisation must always have at least one owner. The organisation, membership, project, and API key APIs use service-layer checks for tenant-scoped reads and mutations; future tenant-scoped routes must do the same instead of performing permission checks in route handlers.

## Domain, schema, and persistence contracts

The current domain layer defines organisation roles (`owner`, `admin`, `member`, `viewer`), service-level permissions, project statuses, project sort options, and audit action names. The Pydantic schemas define the API data contracts, while service workflows own registration, login, current-user business logic, organisation tenant workflows, membership management, project workflows, API key workflows, append-only audit workflows, and RBAC/tenant-context checks for implemented or upcoming protected endpoints.

Password fields use secret-safe request types, response schemas do not include password hashes, and API key metadata schemas do not include raw keys or key hashes. The password utility enforces a configurable local policy and hashes new passwords with pwdlib's recommended Argon2id hasher before persistence. The bearer-token utility signs short-lived local demo access tokens and validates them into an authenticated user principal for `GET /me`. The API key utility generates high-entropy random keys, stores a deterministic SHA-256 hash plus a short prefix, and resolves active keys for project endpoints only. Production systems need real secret management, TLS, token/key rotation, monitoring, and hardened identity review.

The database model stores `password_hash` and `key_hash` fields only; raw API key material is represented only by the intentional one-time API key creation response schema and is not replayed by list, revoke, or idempotency replay responses. API key creation idempotency snapshots store only metadata and a replay note.

Repository classes live under `multi_tenant_saas_api.repositories` and own SQLAlchemy statement construction for business persistence operations. Service and route layers should call these repositories rather than querying ORM models directly. Repository methods that access tenant-owned business data require an organisation scope or a user-membership scope where applicable; RBAC decisions are handled by service-layer tenant contexts.

The initial PostgreSQL schema is managed by Alembic:

```bash
uv run alembic upgrade head
```

The Docker Compose stack includes a local PostgreSQL service and runs migrations before starting the API container for demo convenience. Outside Compose, the migration command and `/readyz` require a separately available database. If PostgreSQL is unreachable, `/readyz` returns a clear `503` not-ready response.

## Documentation

Additional architecture, security, operations, runbook, API walkthrough, and ADR documentation will be added as the corresponding tickets are implemented.
