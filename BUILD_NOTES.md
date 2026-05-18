# BUILD_NOTES.md

## Current state

Tickets 000 through 008 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a FastAPI application shell, the first domain/schema contracts, the initial PostgreSQL persistence foundation, a repository layer that owns SQLAlchemy business data access, authentication utility services, auth API routes for the local demo identity workflow, RBAC/tenant-context services for protected business workflows, and the first tenant-scoped organisation API.

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
- last-owner protection helper for future member removal/downgrade workflows
- `POST /orgs` for bearer-token-authenticated organisation creation, generated-or-explicit unique slugs, creator owner membership creation, and an `organisation.created` audit event
- `GET /orgs` for membership-scoped organisation listing with `limit`/`offset` pagination metadata
- `GET /orgs/{org_id}` for tenant-member organisation reads
- `PATCH /orgs/{org_id}` for owner/admin organisation metadata updates, unique slug enforcement, member/viewer denial, and an `organisation.updated` audit event with secret-safe changed-field metadata

Implemented domain/schema/persistence contracts currently include:

- typed domain identifiers for users, organisations, memberships, projects, API keys, and audit events
- organisation roles (`owner`, `admin`, `member`, `viewer`) and immutable permission mapping helpers
- project statuses and audit action enums
- Pydantic schemas for auth, current-user, organisation, membership, project, API key, audit event, and pagination API contracts
- async SQLAlchemy engine/session factory helpers
- SQLAlchemy ORM models for users, organisations, organisation memberships, projects, API keys, audit events, and idempotency records
- Alembic configuration and initial migration for the PostgreSQL schema
- useful tenant-scoped indexes and uniqueness constraints, including organisation/user membership uniqueness and idempotency scoping indexes
- repository classes for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- tenant-scoped repository methods for membership lists, projects, API key management, audit event reads, and idempotency lookups
- last-owner support queries through the membership repository
- password policy checks backed by `SAAS_API_PASSWORD_MIN_LENGTH`
- password hashing and verification utilities using pwdlib's recommended Argon2id hasher
- bearer access token creation/validation utilities using a local placeholder JWT signing secret setting
- a typed authenticated user principal model used by token validation
- RBAC service DTOs for `CurrentPrincipal` and `TenantContext`
- organisation API service DTOs for public organisation responses, paginated organisation lists, and creator owner membership creation results

Project/member/API-key routes, audit log read APIs, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 008:

- added `multi_tenant_saas_api.services.organisations` with organisation creation, listing, detail, and update workflows behind the service layer
- added `multi_tenant_saas_api.routes.organisations` and registered `POST /orgs`, `GET /orgs`, `GET /orgs/{org_id}`, and `PATCH /orgs/{org_id}` in the FastAPI app
- added a dependency constructor for the organisation workflow service while continuing to resolve current principals through the existing RBAC dependency stack
- made organisation creation generate a slug from the name when omitted, reject duplicate slugs, create an owner membership for the creator, commit atomically, and record a secret-safe `organisation.created` audit event
- made organisation listing use repository membership-scoped queries and pagination metadata so users only see organisations where they are members
- made organisation reads enforce tenant membership and `read_organisation` permission through the RBAC service
- made organisation updates enforce tenant membership and `update_organisation` permission, allow owner/admin roles, deny member/viewer roles, reject duplicate slugs, and record secret-safe `organisation.updated` audit events
- documented the implemented organisation API, slug uniqueness behaviour, and current limitations in `README.md` and `docs/README.md`
- added API tests covering create org, creator owner membership, membership-scoped listing, allowed owner/admin updates, denied member/viewer updates, duplicate slug conflicts, cross-tenant fetch denial, and organisation audit events

Limitations:

- Organisation member management endpoints are still future work; only the implicit creator owner membership is created by the organisation API.
- Project routes, API key management, audit log read routes, and idempotency replay support are not implemented yet.
- API key authentication remains a future ticket; current-principal resolution supports user bearer tokens only.
- The committed JWT secret is a local placeholder only and is not suitable for production.
- Organisation audit metadata intentionally contains no passwords, tokens, raw API keys, or private authentication material.

## Next recommended ticket

Ticket 009.
