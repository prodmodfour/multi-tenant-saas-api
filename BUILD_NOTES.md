# BUILD_NOTES.md

## Current state

Tickets 000, 001, 002, 003, and 004 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a minimal FastAPI application shell, the first domain/schema contracts, the initial PostgreSQL persistence foundation, and a repository layer that owns SQLAlchemy business data access.

Implemented application behaviour currently includes:

- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix, including `SAAS_API_DATABASE_URL`
- docs/OpenAPI disabled by default and explicitly enableable with `SAAS_API_DOCS_ENABLED=true`
- structured JSON logging configuration
- `X-Request-ID` propagation and request-scoped log context
- `GET /healthz`

Implemented domain/schema/persistence contracts currently include:

- typed domain identifiers for users, organisations, memberships, projects, API keys, and audit events
- organisation roles (`owner`, `admin`, `member`, `viewer`) and immutable permission mapping helpers
- project statuses and audit action enums
- Pydantic schemas for planned auth, current-user, organisation, membership, project, API key, audit event, and pagination API contracts
- async SQLAlchemy engine/session factory helpers
- SQLAlchemy ORM models for users, organisations, organisation memberships, projects, API keys, audit events, and idempotency records
- Alembic configuration and initial migration for the PostgreSQL schema
- useful tenant-scoped indexes and uniqueness constraints, including organisation/user membership uniqueness and idempotency scoping indexes
- repository classes for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- tenant-scoped repository methods for membership lists, projects, API key management, audit event reads, and idempotency lookups
- last-owner support queries through the membership repository

Authentication workflows, RBAC enforcement, tenant isolation at service/API level, audit logging integration, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 004:

- added `multi_tenant_saas_api.repositories` with repository classes for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- added create/get/list/update/delete-style methods required for the current domain model while keeping SQLAlchemy statement construction inside the repository layer
- added user-scoped organisation listing, organisation-scoped membership/project/API key/audit queries, and principal/method/path/key-scoped idempotency lookups
- added membership repository helpers for owner counts, other-owner checks, and last-owner detection to support later RBAC workflows
- added soft-delete support at the project repository level using the existing `deleted_at` column
- kept password and API key persistence secret-safe by accepting/storing only `password_hash` and `key_hash` values in repositories
- added repository tests using a fake async session to verify created ORM objects, scoped SQL statement construction, mutation methods, secret-safe fields, idempotency scoping, and last-owner helper behaviour
- updated README current-status and persistence notes to describe the repository layer

Limitations:

- repositories do not commit transactions; future services/routes will own unit-of-work boundaries
- repository tests validate behaviour and SQL statement construction with a fake async session; full online PostgreSQL integration remains future work once local Docker Compose/CI database infrastructure is added
- authentication workflows, password hashing, token handling, RBAC checks, API key authentication, audit service integration, and idempotency replay handling remain future tickets
- no application routes currently open database sessions

## Next recommended ticket

Ticket 005.
