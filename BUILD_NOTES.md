# BUILD_NOTES.md

## Current state

Tickets 000 through 019 are complete. The repository has a Python 3.12 `src/` layout, FastAPI app shell, environment-backed settings, structured JSON logging, request ID propagation, health/readiness/metrics endpoints, async SQLAlchemy persistence, Alembic migrations, repository layer, local demo auth, RBAC/tenant context, organisation APIs, membership management, tenant-scoped project APIs, organisation API key management, API key project authentication, an audit log API, idempotency support for selected unsafe creation endpoints, Prometheus metrics instrumentation, a local Docker Compose stack, local Prometheus/Grafana observability configuration, and GitHub Actions CI.

Implemented application behaviour currently includes:

- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix, including `SAAS_API_DATABASE_URL`
- docs/OpenAPI disabled by default and explicitly enableable with `SAAS_API_DOCS_ENABLED=true`
- structured JSON logging configuration
- `X-Request-ID` propagation and request-scoped log context
- request-scoped async SQLAlchemy session dependency wiring
- `GET /healthz`
- `GET /readyz` with an aggregate readiness response and a PostgreSQL `SELECT 1` dependency check that returns `503` when the database is unavailable
- `GET /metrics` exposing Prometheus text metrics from an app-local registry
- HTTP request metrics for total requests and request duration using low-cardinality route-template labels
- Dockerfile using Python 3.12, uv-based dependency installation, a non-root runtime user, Uvicorn, and a `/healthz` container health check
- `docker-compose.yml` local demo stack with `api`, `postgres`, `prometheus`, and `grafana` services using public-safe placeholder configuration
- Compose API startup that waits for PostgreSQL, runs `alembic upgrade head`, and then starts Uvicorn for local demo convenience
- Prometheus scrape configuration at `observability/prometheus/prometheus.yml` for the Compose API target `api:8000/metrics`
- Grafana provisioning for a Prometheus datasource and file-loaded dashboard under `observability/grafana/`
- basic Grafana dashboard JSON for API request rate, latency percentiles, auth attempts, domain workflow counters, idempotency outcomes, and audit events
- GitHub Actions CI workflow at `.github/workflows/ci.yml` using Python 3.12, uv, a PostgreSQL service container, shell syntax checks, automation guardrails, Ruff, mypy, Docker Compose config validation, Alembic migration upgrade, and pytest with coverage
- automation guardrail scripts for public-safety/private-term scanning, route-layer architecture boundary checks, and secret-looking response schema checks
- `POST /auth/register` for local demo user registration with hashed password persistence only
- `POST /auth/login` for local demo bearer-token login
- auth attempt metrics for registration/login success and failure outcomes
- `GET /me` for current active user and membership summaries
- current-principal resolution from bearer tokens into secret-safe principal DTOs
- RBAC tenant-context creation with organisation lookup, membership lookup, role permissions, and explicit not-found/access-denied/permission-denied service errors
- last-owner protection helper used by member removal/downgrade workflows
- `POST /orgs` for bearer-token-authenticated organisation creation, generated-or-explicit unique slugs, creator owner membership creation, `organisation.created` audit events, and an organisations-created metric
- `GET /orgs` for membership-scoped organisation listing with `limit`/`offset` pagination metadata
- `GET /orgs/{org_id}` for tenant-member organisation reads
- `PATCH /orgs/{org_id}` for owner/admin organisation metadata updates and `organisation.updated` audit events
- `GET /orgs/{org_id}/members` for owner/admin membership listing with public user summaries and pagination metadata
- `POST /orgs/{org_id}/members` for owner/admin member creation of existing users, duplicate membership rejection, admin owner-grant denial, and `member.added` audit events
- `PATCH /orgs/{org_id}/members/{user_id}` for owner/admin role changes, admin owner-operation denial, last-owner downgrade protection, and `member.role_changed` audit events
- `DELETE /orgs/{org_id}/members/{user_id}` for owner/admin member removal, admin owner-removal denial, last-owner removal protection, and `member.removed` audit events
- `POST /orgs/{org_id}/projects` for member/admin/owner project creation with viewer write denial, API key project access, `project.created` audit events, and a projects-created metric
- `GET /orgs/{org_id}/projects` for tenant-scoped non-deleted project listing with `limit`/`offset` pagination, optional `status` filtering, optional case-insensitive `name` search, and `created_at`/`name`/`status` sorting
- `GET /orgs/{org_id}/projects/{project_id}` for tenant-scoped project reads that combine organisation ID and project ID so cross-tenant project IDs are not accessible
- `PATCH /orgs/{org_id}/projects/{project_id}` for member/admin/owner/API-key project updates, nullable description clearing, viewer write denial, and `project.updated` audit events
- `DELETE /orgs/{org_id}/projects/{project_id}` for member/admin/owner/API-key soft deletes, viewer write denial, default read/list exclusion, and `project.deleted` audit events
- `POST /orgs/{org_id}/api-keys` for owner/admin API key creation with one-time raw key response, hashed key persistence, stored prefix metadata, member/viewer denial, `api_key.created` audit events, and an API-keys-created metric
- `GET /orgs/{org_id}/api-keys` for owner/admin paginated API key metadata listing that never returns raw keys or key hashes
- `DELETE /orgs/{org_id}/api-keys/{api_key_id}` for owner/admin API key revocation, revoked-key authentication denial, `api_key.revoked` audit events, and an API-keys-revoked metric
- `GET /orgs/{org_id}/audit-events` for owner/admin audit log reads with tenant scoping, `limit`/`offset` pagination metadata, member/viewer denial, and cross-tenant denial before audit rows are listed
- append-only audit service integration for important business operations, with secret-field metadata rejection, no public update/delete audit workflow, and audit-events-recorded metrics labelled by action
- project endpoint authentication using either user bearer tokens with RBAC membership checks or active organisation-scoped API keys for project read/write access
- API key tenant isolation so keys cannot access other organisations and cannot manage members, API keys, or audit logs because those routes require user access tokens
- optional `Idempotency-Key` support for `POST /orgs`, `POST /orgs/{org_id}/projects`, and `POST /orgs/{org_id}/api-keys`
- idempotency records scoped by principal type/ID, HTTP method, path, request body hash, and organisation ID where applicable
- idempotent replay responses for matching keys/bodies with `Idempotency-Replayed: true` and an idempotency replay metric
- `409 Conflict` responses for reused idempotency keys with changed request bodies, without exposing body hashes, plus an idempotency conflict metric
- current tenant permission checks before organisation-scoped project/API key idempotent replay
- API key creation idempotency snapshots that omit raw key material and return only metadata plus a replay note on replay

Implemented domain/schema/persistence contracts currently include:

- typed domain identifiers for users, organisations, memberships, projects, API keys, and audit events
- organisation roles (`owner`, `admin`, `member`, `viewer`) and immutable permission mapping helpers
- project statuses, project sort options, and audit action enums
- Pydantic schemas for auth, current-user, organisation, membership, project, API key, audit event, and pagination API contracts
- async SQLAlchemy engine/session factory helpers
- SQLAlchemy ORM models for users, organisations, organisation memberships, projects, API keys, audit events, and idempotency records
- Alembic configuration and initial migration for the PostgreSQL schema
- repository classes for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- tenant-scoped repository methods for membership lists, sortable/filterable project access, API key management, audit event reads, and idempotency lookups
- password policy checks backed by `SAAS_API_PASSWORD_MIN_LENGTH`
- password hashing and verification utilities using pwdlib's recommended Argon2id hasher
- bearer access token creation/validation utilities using a local placeholder JWT signing secret setting
- deterministic high-entropy API key generation and SHA-256 hashing utilities that persist only key hashes plus prefixes
- service-layer DTOs for public auth, organisation, membership, project, API key, audit, RBAC, readiness, and idempotency workflows
- secret-field rejection for idempotency response snapshots so obvious password, bearer-token, raw-key, and key-hash fields are not persisted for replay

CI is implemented with local placeholder settings only and runs Alembic migrations against a PostgreSQL service container.

## Quality gates

Ran `scripts/quality-gate.sh` successfully. The gate completed:

- shell syntax checks for scripts
- `uv sync --locked --all-groups`
- Ruff check
- Ruff format check
- mypy strict checks for `src` and `tests`
- pytest with coverage (`122 passed`)
- Docker Compose config validation
- public-safety, architecture-boundary, and secret-leakage guardrails

## Public-safety notes

This project is an independent public portfolio project.

Do not add employer code, private data, internal URLs, credentials, screenshots, non-public architecture, or anything implying employer endorsement.

Do not commit real secrets.

Do not log passwords, password hashes, bearer tokens, raw API keys, or private authentication material.

Store password hashes only.

Store API key hashes only.

The committed `example.env` and `docker-compose.yml` use local placeholder values only and are not suitable for production.

## Latest cycle notes

Implemented Ticket 019:

- added `scripts/guardrails.py` plus shell wrappers for public-safety/private-term checks, route-layer architecture boundary checks, and secret-looking response schema checks
- public-safety guardrail scans tracked/non-ignored files for committed `.env` files, high-confidence secret token shapes, internal-looking hostnames, sample-file secret values, and locally supplied forbidden terms via `SAAS_API_FORBIDDEN_TERMS_FILE`
- architecture guardrail rejects obvious route-layer imports of SQLAlchemy/database/repository modules and direct persistence or hashing/token utility calls in route modules
- secret-leakage guardrail rejects secret-looking fields on public response schema classes while allowing the intentional `LoginResponse.access_token` and one-time `APIKeyCreateResponse.raw_key` fields
- wired the guardrail scripts into GitHub Actions CI as required commands and documented the guardrails in README/docs
- added guardrail tests covering passing placeholder examples, `.env`/secret pattern failures, local forbidden terms, raw bearer examples, route persistence violations, and response secret-field violations

Quality gates run:

- targeted check completed successfully: `uv run pytest tests/test_guardrails.py tests/test_ci_workflow.py`
- targeted static checks completed successfully: `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy tests/test_guardrails.py tests/test_ci_workflow.py`
- `scripts/quality-gate.sh` completed successfully after implementation
- gate covered shell syntax checks, `uv sync --locked --all-groups`, Ruff check, Ruff format check, mypy strict checks, pytest with coverage (`122 passed`), Docker Compose config validation, and all three guardrail scripts

Limitations:

- Automation guardrails are heuristic static checks, not a substitute for reviewed secret scanning, security review, or production data-loss prevention controls.
- The public-safety forbidden-term list is intentionally supplied from a local uncommitted file; no private/employer terms are committed to the repository.
- The architecture guardrail catches obvious route-to-database violations but cannot prove every future workflow respects layering or tenant scoping.
- The secret-response guardrail checks schema field names and still relies on service/API tests and review to prove runtime responses remain secret-safe.
- Existing project limitations remain: Compose credentials and JWT settings are local placeholders only, observability is local-demo oriented, API key scopes are coarse-grained, and idempotency cleanup/concurrency hardening is not implemented.

## Next recommended ticket

Ticket 020.
