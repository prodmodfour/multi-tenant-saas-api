# BUILD_NOTES.md

## Current state

Tickets 000, 001, 002, and 003 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a minimal FastAPI application shell, the first domain/schema contracts, and the initial PostgreSQL persistence foundation.

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

Repository methods, authentication workflows, RBAC enforcement, tenant isolation at service/API level, audit logging integration, idempotency behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 003:

- added SQLAlchemy, asyncpg, and Alembic dependencies
- added `multi_tenant_saas_api.database` with shared metadata naming conventions, ORM models, and async engine/session factory helpers
- added `SAAS_API_DATABASE_URL` to settings with a local placeholder PostgreSQL async URL
- modelled the required tables: `users`, `organisations`, `organisation_memberships`, `projects`, `api_keys`, `audit_events`, and `idempotency_records`
- included hashed-storage fields (`password_hash`, `key_hash`) and did not add raw password/API key persistence fields
- added tenant-scoped indexes, uniqueness constraints, nullable audit organisation support, and scoped idempotency uniqueness indexes
- added Alembic configuration and initial PostgreSQL migration at `alembic/versions/0001_initial_schema.py`
- added tests for model metadata, constraints/indexes, secret-safe storage fields, async engine/session configuration, and offline Alembic SQL rendering
- updated README configuration/current-status/persistence notes

Limitations:

- the persistence layer defines models and migrations only; repository methods and business workflows are planned for Ticket 004 and later tickets
- no application routes currently open database sessions
- no local PostgreSQL or Docker Compose stack is included yet; running Alembic online requires a separately available database until Ticket 016
- password hashing, token authentication, RBAC checks, API key authentication, audit service integration, and idempotency replay handling remain future tickets

## Next recommended ticket

Ticket 004.
