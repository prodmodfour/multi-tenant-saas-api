# BUILD_NOTES.md

## Current state

Tickets 000 through 010 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a FastAPI application shell, the first domain/schema contracts, the initial PostgreSQL persistence foundation, a repository layer that owns SQLAlchemy business data access, authentication utility services, auth API routes for the local demo identity workflow, RBAC/tenant-context services for protected business workflows, the first tenant-scoped organisation API, organisation membership management API workflows, and tenant-isolated project API workflows.

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
- a typed authenticated user principal model used by token validation
- RBAC service DTOs for `CurrentPrincipal` and `TenantContext`
- organisation API service DTOs for public organisation responses, paginated organisation lists, and creator owner membership creation results
- membership API service DTOs for public membership responses, embedded public user summaries, and paginated membership lists
- project API service DTOs for public project responses and paginated project lists

API key management routes, audit log read APIs, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 010:

- added `multi_tenant_saas_api.services.projects` with project create, list, get, update, and soft-delete workflows behind the service layer
- added `multi_tenant_saas_api.routes.projects` and registered `POST /orgs/{org_id}/projects`, `GET /orgs/{org_id}/projects`, `GET /orgs/{org_id}/projects/{project_id}`, `PATCH /orgs/{org_id}/projects/{project_id}`, and `DELETE /orgs/{org_id}/projects/{project_id}` in the FastAPI app
- added a dependency constructor for the project workflow service while continuing to resolve current principals through the existing RBAC dependency stack
- added project sort domain options for `created_at`, `name`, and `status` plus `asc`/`desc` sort directions
- extended the project repository list query with validated sorting while preserving organisation scoping, status filtering, name search, and soft-delete exclusion
- made project creation, update, and deletion require tenant membership plus `write_projects`, allowing `owner`, `admin`, and `member` roles while denying `viewer`
- made project listing and detail reads require tenant membership plus `read_projects`, so `viewer` can read projects but all project lookups remain scoped by organisation ID
- recorded secret-safe `project.created`, `project.updated`, and `project.deleted` audit events without passwords, tokens, bearer credentials, raw API keys, or private authentication material
- documented the implemented project API, filters, sorting, soft-delete behaviour, RBAC policy, and tenant-isolation behaviour in `README.md` and `docs/README.md`
- added API tests covering project create/read/update/delete, tenant isolation, viewer read allowed/write denied, pagination, filtering, sorting, audit events, and absence of password leakage in project responses

Limitations:

- API key management, audit log read routes, and idempotency replay support are not implemented yet.
- API key authentication remains a future ticket; current-principal resolution supports user bearer tokens only.
- The committed JWT secret is a local placeholder only and is not suitable for production.
- Project audit metadata intentionally contains no passwords, password hashes, bearer tokens, raw API keys, or private authentication material.

## Next recommended ticket

Ticket 011.
