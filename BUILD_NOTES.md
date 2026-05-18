# BUILD_NOTES.md

## Current state

Tickets 000 through 007 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a FastAPI application shell, the first domain/schema contracts, the initial PostgreSQL persistence foundation, a repository layer that owns SQLAlchemy business data access, authentication utility services, auth API routes for the local demo identity workflow, and RBAC/tenant-context services for protected business workflows.

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

Organisation/project/member/API-key routes, broader audit logging integration, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 007:

- added `multi_tenant_saas_api.services.rbac` with `PrincipalResolverService`, `RBACService`, secret-safe `CurrentPrincipal`, and `TenantContext`
- added current-principal resolution that validates bearer access tokens, loads active users through the repository layer, and collapses invalid/expired/missing/inactive users into a safe authentication error
- added tenant-context lookup that loads organisations and memberships through repositories, grants immutable role permissions, and raises explicit organisation-not-found, tenant-access-denied, and permission-denied service errors
- added service-level last-owner protection for member removals or role changes away from `owner`
- added FastAPI dependency helpers for shared bearer-token extraction, RBAC service construction, and current-principal resolution for future protected routes
- refactored `GET /me` internals to reuse the principal resolver while preserving safe bearer-token failure behaviour and avoiding password-hash exposure
- documented the role model and tenant access policy in `README.md` and `docs/README.md`
- added service tests covering current-principal resolution, owner/admin/member/viewer permission behaviour, unknown organisations, non-member rejection, and last-owner protection

Limitations:

- Tenant-scoped organisation, membership, project, API-key, and audit routes are not implemented yet, so the new RBAC services are groundwork for future tickets rather than broadly exposed API behaviour.
- API key authentication remains a future ticket; current-principal resolution supports user bearer tokens only.
- The committed JWT secret is a local placeholder only and is not suitable for production.
- Authentication audit events currently use empty metadata to avoid accidental secret or private-data leakage.

## Next recommended ticket

Ticket 008.
