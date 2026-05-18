# BUILD_NOTES.md

## Current state

Tickets 000 through 015 are complete. The repository has a Python 3.12 `src/` layout, FastAPI app shell, environment-backed settings, structured JSON logging, request ID propagation, health/readiness/metrics endpoints, async SQLAlchemy persistence, Alembic migrations, repository layer, local demo auth, RBAC/tenant context, organisation APIs, membership management, tenant-scoped project APIs, organisation API key management, API key project authentication, an audit log API, idempotency support for selected unsafe creation endpoints, and Prometheus metrics instrumentation.

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

Docker and CI are not implemented yet. Prometheus scrape configuration, Grafana dashboards, and container observability wiring are deferred to later tickets.

## Quality gates

Ran `scripts/quality-gate.sh` successfully. The gate completed:

- shell syntax checks for scripts
- `uv sync --locked --all-groups`
- Ruff check
- Ruff format check
- mypy strict checks for `src` and `tests`
- pytest with coverage (`104 passed`)

## Public-safety notes

This project is an independent public portfolio project.

Do not add employer code, private data, internal URLs, credentials, screenshots, non-public architecture, or anything implying employer endorsement.

Do not commit real secrets.

Do not log passwords, password hashes, bearer tokens, raw API keys, or private authentication material.

Store password hashes only.

Store API key hashes only.

The committed `example.env` uses local placeholder values only and is not suitable for production.

## Latest cycle notes

Implemented Ticket 015:

- added `prometheus-client` as an application dependency
- added `multi_tenant_saas_api.observability.metrics.MetricsService` with an app-local Prometheus registry and a no-op recorder for service tests/default construction
- added request metrics middleware for `saas_api_requests_total` and `saas_api_request_duration_seconds`, using route-template path labels to avoid raw tenant/resource ID cardinality
- added `GET /metrics` Prometheus text exposition
- wired metrics recording into auth workflows for registration/login success and failure attempts
- wired organisation/project/API-key services to record created/revoked counters after successful commits
- wired the append-only audit service to record `saas_api_audit_events_recorded_total` labelled by audit action
- wired idempotency replay/conflict detection to record replay and conflict counters
- added tests for the metrics endpoint, key metric names, route-template request labels, direct metric counters, and representative auth/organisation/project/API-key/audit/idempotency integration points
- updated README and docs/README observability documentation

Quality gates run:

- `scripts/quality-gate.sh` completed successfully after implementation
- gate covered shell syntax checks, `uv sync --locked --all-groups`, Ruff check, Ruff format check, mypy strict checks, and pytest with coverage (`104 passed`)

Limitations:

- Docker Compose and CI are not implemented yet.
- Prometheus scrape configuration, Grafana dashboards, and container observability wiring are deferred to later tickets.
- Metrics are process-local; multi-process deployment aggregation and long-term retention would require production observability infrastructure.
- API keys currently have fixed project read/write capability for their owning organisation; fine-grained API key scopes are not implemented.
- Idempotency expiry cleanup and simultaneous first-request concurrency hardening are not implemented; production systems should use transactional first-writer handling and operational cleanup.
- API key hashes use deterministic SHA-256 over high-entropy generated keys for demo lookup; production systems may add a dedicated secret pepper or managed key service.
- The committed JWT secret is a local placeholder only and is not suitable for production.
- Audit and idempotency metadata intentionally contain no passwords, password hashes, bearer tokens, raw API keys, key hashes, or private authentication material.

## Next recommended ticket

Ticket 016.
