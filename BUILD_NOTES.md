# BUILD_NOTES.md

## Current state

Tickets 000, 001, 002, 003, 004, and 005 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a minimal FastAPI application shell, the first domain/schema contracts, the initial PostgreSQL persistence foundation, a repository layer that owns SQLAlchemy business data access, and authentication utility services for password hashing plus bearer access tokens.

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
- password policy checks backed by `SAAS_API_PASSWORD_MIN_LENGTH`
- password hashing and verification utilities using pwdlib's recommended Argon2id hasher
- bearer access token creation/validation utilities using a local placeholder JWT signing secret setting
- a typed authenticated user principal model for future auth dependencies

Auth API routes/workflows, RBAC enforcement, tenant isolation at service/API level, audit logging integration, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 005:

- added `multi_tenant_saas_api.services.auth` with password policy validation, Argon2id password hashing/verification, bearer access token creation/validation, and an authenticated user principal model
- added `pwdlib[argon2]` for password hashing and `PyJWT` for signed bearer access tokens
- extended settings with `SAAS_API_JWT_SECRET`, `SAAS_API_JWT_ISSUER`, `SAAS_API_ACCESS_TOKEN_TTL_SECONDS`, and `SAAS_API_PASSWORD_MIN_LENGTH`
- kept JWT secrets as `SecretStr` in settings so repr/logging masks the value
- added tests for password hash safety, correct/wrong password verification, password policy failures, token validation, expired token handling, invalid token handling, and settings-backed auth service construction
- updated README configuration and security notes to describe auth utilities and production secret-management requirements

Limitations:

- authentication API routes are not implemented yet; future services/routes will call these utilities for registration, login, and current-user workflows
- token validation currently supports user bearer tokens only; API key authentication remains a future ticket
- the committed JWT secret is a local placeholder only and is not suitable for production
- repositories still do not commit transactions; future services/routes will own unit-of-work boundaries
- no application routes currently open database sessions

## Next recommended ticket

Ticket 006.
