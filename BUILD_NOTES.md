# BUILD_NOTES.md

## Current state

Tickets 000 through 012 are complete. The repository has a Python 3.12 `src/` layout, FastAPI app shell, environment-backed settings, structured JSON logging, request ID propagation, async SQLAlchemy persistence, Alembic migrations, repository layer, local demo auth, RBAC/tenant context, organisation APIs, membership management, tenant-scoped project APIs, organisation API key management, API key project authentication, and an audit log API.

Implemented application behaviour currently includes:

- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix, including `SAAS_API_DATABASE_URL`
- docs/OpenAPI disabled by default and explicitly enableable with `SAAS_API_DOCS_ENABLED=true`
- structured JSON logging configuration
- `X-Request-ID` propagation and request-scoped log context
- request-scoped async SQLAlchemy session dependency wiring
- `GET /healthz`
- `POST /auth/register` for local demo user registration with hashed password persistence only
- `POST /auth/login` for local demo bearer-token login
- `GET /me` for current active user and membership summaries
- current-principal resolution from bearer tokens into secret-safe principal DTOs
- RBAC tenant-context creation with organisation lookup, membership lookup, role permissions, and explicit not-found/access-denied/permission-denied service errors
- last-owner protection helper used by member removal/downgrade workflows
- `POST /orgs` for bearer-token-authenticated organisation creation, generated-or-explicit unique slugs, creator owner membership creation, and `organisation.created` audit events
- `GET /orgs` for membership-scoped organisation listing with `limit`/`offset` pagination metadata
- `GET /orgs/{org_id}` for tenant-member organisation reads
- `PATCH /orgs/{org_id}` for owner/admin organisation metadata updates and `organisation.updated` audit events
- `GET /orgs/{org_id}/members` for owner/admin membership listing with public user summaries and pagination metadata
- `POST /orgs/{org_id}/members` for owner/admin member creation of existing users, duplicate membership rejection, admin owner-grant denial, and `member.added` audit events
- `PATCH /orgs/{org_id}/members/{user_id}` for owner/admin role changes, admin owner-operation denial, last-owner downgrade protection, and `member.role_changed` audit events
- `DELETE /orgs/{org_id}/members/{user_id}` for owner/admin member removal, admin owner-removal denial, last-owner removal protection, and `member.removed` audit events
- `POST /orgs/{org_id}/projects` for member/admin/owner project creation with viewer write denial, API key project access, and `project.created` audit events
- `GET /orgs/{org_id}/projects` for tenant-scoped non-deleted project listing with `limit`/`offset` pagination, optional `status` filtering, optional case-insensitive `name` search, and `created_at`/`name`/`status` sorting
- `GET /orgs/{org_id}/projects/{project_id}` for tenant-scoped project reads that combine organisation ID and project ID so cross-tenant project IDs are not accessible
- `PATCH /orgs/{org_id}/projects/{project_id}` for member/admin/owner/API-key project updates, nullable description clearing, viewer write denial, and `project.updated` audit events
- `DELETE /orgs/{org_id}/projects/{project_id}` for member/admin/owner/API-key soft deletes, viewer write denial, default read/list exclusion, and `project.deleted` audit events
- `POST /orgs/{org_id}/api-keys` for owner/admin API key creation with one-time raw key response, hashed key persistence, stored prefix metadata, member/viewer denial, and `api_key.created` audit events
- `GET /orgs/{org_id}/api-keys` for owner/admin paginated API key metadata listing that never returns raw keys or key hashes
- `DELETE /orgs/{org_id}/api-keys/{api_key_id}` for owner/admin API key revocation, revoked-key authentication denial, and `api_key.revoked` audit events
- `GET /orgs/{org_id}/audit-events` for owner/admin audit log reads with tenant scoping, `limit`/`offset` pagination metadata, member/viewer denial, and cross-tenant denial before audit rows are listed
- append-only audit service integration for important business operations, with secret-field metadata rejection and no public update/delete audit workflow
- project endpoint authentication using either user bearer tokens with RBAC membership checks or active organisation-scoped API keys for project read/write access
- API key tenant isolation so keys cannot access other organisations and cannot manage members, API keys, or audit logs because those routes require user access tokens

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
- service-layer DTOs for public auth, organisation, membership, project, API key, audit, and RBAC workflows

Idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

## Quality gates

Ran `scripts/quality-gate.sh` successfully. The gate completed:

- shell syntax checks for scripts
- `uv sync --locked --all-groups`
- Ruff check
- Ruff format check
- mypy strict checks for `src` and `tests`
- pytest with coverage (`91 passed`)

## Public-safety notes

This project is an independent public portfolio project.

Do not add employer code, private data, internal URLs, credentials, screenshots, non-public architecture, or anything implying employer endorsement.

Do not commit real secrets.

Do not log passwords, password hashes, bearer tokens, raw API keys, or private authentication material.

Store password hashes only.

Store API key hashes only.

The committed `example.env` uses local placeholder values only and is not suitable for production.

## Latest cycle notes

Implemented Ticket 012:

- added `multi_tenant_saas_api.services.audit` with an append-only `AuditService`, secret-field metadata rejection, public audit DTOs, and authorised organisation audit listing
- refactored registration/login, organisation, membership, project, and API key business workflows to write audit events through the audit service instead of writing directly from each workflow to the audit repository
- added `multi_tenant_saas_api.routes.audit` and registered `GET /orgs/{org_id}/audit-events`
- added dependency wiring for the audit service with RBAC tenant-context checks
- made audit log reads require `read_audit_events`, allowing `owner` and `admin` users while explicitly denying `member`, `viewer`, non-members, cross-tenant users, and API key principals
- kept audit logs append-only at the API/service layer: there is no public create/update/delete audit route and no service update/delete workflow
- ensured audit responses are tenant-scoped, newest-first through the repository, and paginated with the existing pagination metadata contract
- updated README and docs to describe audit read behaviour, append-only design, RBAC policy, and secret-safe metadata handling
- added API/service tests covering audit event creation, metadata secret rejection, owner/admin audit reads, member/viewer denial, cross-tenant denial before listing, pagination, tenant-scoped SQL, and absence of secret fields in returned audit metadata

Limitations:

- Idempotency replay support is not implemented yet.
- Readiness checks, Prometheus metrics, Docker Compose, and CI are not implemented yet.
- API keys currently have fixed project read/write capability for their owning organisation; fine-grained API key scopes are not implemented.
- API key hashes use deterministic SHA-256 over high-entropy generated keys for demo lookup; production systems may add a dedicated secret pepper or managed key service.
- The committed JWT secret is a local placeholder only and is not suitable for production.
- Audit metadata intentionally contains no passwords, password hashes, bearer tokens, raw API keys, key hashes, or private authentication material.

## Next recommended ticket

Ticket 013.
