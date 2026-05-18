# BUILD_NOTES.md

## Current state

Tickets 000 through 011 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a FastAPI application shell, the first domain/schema contracts, the initial PostgreSQL persistence foundation, a repository layer that owns SQLAlchemy business data access, authentication utility services, auth API routes for the local demo identity workflow, RBAC/tenant-context services for protected business workflows, the first tenant-scoped organisation API, organisation membership management API workflows, tenant-isolated project API workflows, and organisation-scoped API key management plus project endpoint API key authentication.

Implemented application behaviour currently includes:

- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix, including `SAAS_API_DATABASE_URL`
- docs/OpenAPI disabled by default and explicitly enableable with `SAAS_API_DOCS_ENABLED=true`
- structured JSON logging configuration
- `X-Request-ID` propagation and request-scoped log context
- request-scoped async SQLAlchemy session dependency wiring
- `GET /healthz`
- `POST /auth/register` for local demo user registration
- `POST /auth/login` for local demo bearer-token login
- `GET /me` for current active user and membership summaries
- successful registration/login audit events with nullable organisation ID and empty secret-safe metadata
- current-principal resolution from bearer tokens into secret-safe principal DTOs
- RBAC tenant-context creation with organisation lookup, membership lookup, role permissions, and explicit not-found/access-denied/permission-denied service errors
- last-owner protection helper used by member removal/downgrade workflows
- `POST /orgs` for bearer-token-authenticated organisation creation, generated-or-explicit unique slugs, creator owner membership creation, and an `organisation.created` audit event
- `GET /orgs` for membership-scoped organisation listing with `limit`/`offset` pagination metadata
- `GET /orgs/{org_id}` for tenant-member organisation reads
- `PATCH /orgs/{org_id}` for owner/admin organisation metadata updates, unique slug enforcement, member/viewer denial, and an `organisation.updated` audit event with secret-safe changed-field metadata
- `GET /orgs/{org_id}/members` for owner/admin membership listing with public user summaries and pagination metadata
- `POST /orgs/{org_id}/members` for owner/admin member creation of existing users, duplicate membership rejection, admin owner-grant denial, and a `member.added` audit event
- `PATCH /orgs/{org_id}/members/{user_id}` for owner/admin role changes, admin owner-operation denial, last-owner downgrade protection, and a `member.role_changed` audit event
- `DELETE /orgs/{org_id}/members/{user_id}` for owner/admin member removal, admin owner-removal denial, last-owner removal protection, and a `member.removed` audit event
- `POST /orgs/{org_id}/projects` for member/admin/owner project creation with viewer write denial and a `project.created` audit event
- `GET /orgs/{org_id}/projects` for tenant-scoped non-deleted project listing with `limit`/`offset` pagination, optional `status` filtering, optional case-insensitive `name` search, and `created_at`/`name`/`status` sorting
- `GET /orgs/{org_id}/projects/{project_id}` for tenant-scoped project reads that combine organisation ID and project ID so cross-tenant project IDs are not accessible
- `PATCH /orgs/{org_id}/projects/{project_id}` for member/admin/owner project updates, nullable description clearing, viewer write denial, and a `project.updated` audit event
- `DELETE /orgs/{org_id}/projects/{project_id}` for member/admin/owner soft deletes, viewer write denial, default read/list exclusion, and a `project.deleted` audit event
- `POST /orgs/{org_id}/api-keys` for owner/admin API key creation with one-time raw key response, hashed key persistence, stored prefix metadata, member/viewer denial, and an `api_key.created` audit event
- `GET /orgs/{org_id}/api-keys` for owner/admin paginated API key metadata listing that never returns raw keys or key hashes
- `DELETE /orgs/{org_id}/api-keys/{api_key_id}` for owner/admin API key revocation, revoked-key authentication denial, and an `api_key.revoked` audit event
- project endpoint authentication using either user bearer tokens with RBAC membership checks or active organisation-scoped API keys for project read/write access
- API key tenant isolation so keys cannot access other organisations and cannot manage members or API keys because those routes continue to require user access tokens

Implemented domain/schema/persistence contracts currently include:

- typed domain identifiers for users, organisations, memberships, projects, API keys, and audit events
- organisation roles (`owner`, `admin`, `member`, `viewer`) and immutable permission mapping helpers
- project statuses, project sort options, and audit action enums
- Pydantic schemas for auth, current-user, organisation, membership, project, API key, audit event, and pagination API contracts
- async SQLAlchemy engine/session factory helpers
- SQLAlchemy ORM models for users, organisations, organisation memberships, projects, API keys, audit events, and idempotency records
- Alembic configuration and initial migration for the PostgreSQL schema
- useful tenant-scoped indexes and uniqueness constraints, including organisation/user membership uniqueness and idempotency scoping indexes
- repository classes for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- tenant-scoped repository methods for membership lists, sortable/filterable project access, API key management, audit event reads, and idempotency lookups
- last-owner support queries through the membership repository
- password policy checks backed by `SAAS_API_PASSWORD_MIN_LENGTH`
- password hashing and verification utilities using pwdlib's recommended Argon2id hasher
- bearer access token creation/validation utilities using a local placeholder JWT signing secret setting
- typed authenticated user and API key principal models used by token/API key validation
- deterministic high-entropy API key generation and SHA-256 hashing utilities that persist only key hashes plus prefixes
- RBAC service DTOs for `CurrentPrincipal` and `TenantContext`
- organisation API service DTOs for public organisation responses, paginated organisation lists, and creator owner membership creation results
- membership API service DTOs for public membership responses, embedded public user summaries, and paginated membership lists
- project API service DTOs for public project responses and paginated project lists
- API key API service DTOs for public key metadata, one-time creation responses, revocation responses, paginated key lists, and API key principals

Audit log read APIs, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

## Quality gates

Ran `scripts/quality-gate.sh` successfully. The gate completed:

- shell syntax checks for scripts
- `uv sync --locked --all-groups`
- Ruff check
- Ruff format check
- mypy strict checks for `src` and `tests`
- pytest with coverage

## Public-safety notes

This project is an independent public portfolio project.

Do not add employer code, private data, internal URLs, credentials, screenshots, non-public architecture, or anything implying employer endorsement.

Do not commit real secrets.

Do not log passwords, password hashes, bearer tokens, raw API keys, or private authentication material.

Store password hashes only.

Store API key hashes only.

The committed `example.env` uses local placeholder values only and is not suitable for production.

## Latest cycle notes

Implemented Ticket 011:

- added `multi_tenant_saas_api.services.api_keys` with API key creation, metadata listing, revocation, deterministic hashing, high-entropy raw key generation, and API key-aware project principal resolution behind the service layer
- added `multi_tenant_saas_api.routes.api_keys` and registered `POST /orgs/{org_id}/api-keys`, `GET /orgs/{org_id}/api-keys`, and `DELETE /orgs/{org_id}/api-keys/{api_key_id}` in the FastAPI app
- added dependency constructors for API key management and API key-aware project authentication while leaving organisation, membership, and API key management routes user-token-only
- extended project route authentication to accept either a user bearer access token or an active organisation-scoped API key
- made API key creation/list/revoke require tenant membership plus `manage_api_keys`, allowing `owner` and `admin` users while denying `member`, `viewer`, non-members, and API key principals
- generated raw API keys only for the one-time create response, stored only SHA-256 key hashes plus short prefixes, and ensured list/revoke responses never include raw key material or key hashes
- updated API key authentication to ignore revoked keys, update `last_used_at` on successful key authentication, and reject cross-tenant project access
- recorded secret-safe `api_key.created` and `api_key.revoked` audit events without passwords, password hashes, bearer tokens, raw API keys, key hashes, or private authentication material
- updated project audit writes so API key-driven project mutations record `actor_api_key_id` instead of a user actor
- documented API key management, API key project authentication, tenant isolation, and raw-key handling in `README.md` and `docs/README.md`
- added API tests covering one-time raw key create response behaviour, hashed persistence, metadata-only listing, revocation, revoked-key denial, API key project read/write access, cross-tenant denial, and API key inability to manage members or API keys

Limitations:

- Audit log read routes and idempotency replay support are not implemented yet.
- API keys currently have a fixed project read/write capability for their owning organisation; fine-grained API key scopes are not implemented.
- API key hashes use deterministic SHA-256 over high-entropy generated keys for demo lookup; production systems may add a dedicated secret pepper or managed key service.
- The committed JWT secret is a local placeholder only and is not suitable for production.
- API key audit metadata intentionally contains no passwords, password hashes, bearer tokens, raw API keys, key hashes, or private authentication material.

## Next recommended ticket

Ticket 012.
