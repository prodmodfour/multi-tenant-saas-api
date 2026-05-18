# BUILD_NOTES.md

## Current state

Tickets 000, 001, 002, 003, 004, 005, and 006 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a FastAPI application shell, the first domain/schema contracts, the initial PostgreSQL persistence foundation, a repository layer that owns SQLAlchemy business data access, authentication utility services, and auth API routes for the local demo identity workflow.

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
- a typed authenticated user principal model used by `GET /me`

RBAC enforcement, tenant isolation at service/API level beyond current-user membership scoping, organisation/project/member/API-key routes, broader audit logging integration, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 006:

- added `multi_tenant_saas_api.services.auth_api` for registration, login, and current-user workflows behind a service layer
- added FastAPI dependency helpers for app settings, request-scoped database sessions, and auth workflow service construction
- wired the app factory to create an async SQLAlchemy engine/session factory and dispose the engine on lifespan shutdown
- added auth routes for `POST /auth/register`, `POST /auth/login`, and `GET /me`
- registration now normalises email addresses, rejects duplicates, hashes passwords before persistence, commits the unit of work, and emits a secret-safe `user.registered` audit event
- login now returns a bearer token for valid credentials, uses one generic safe error for unknown email/wrong password/inactive user, commits the audit unit of work, and emits a secret-safe `user.logged_in` audit event
- `GET /me` validates bearer access tokens and returns the active user plus organisation membership summaries without exposing password hashes
- added API tests covering registration, duplicate email rejection, password hash storage, login success, generic login failures, current-user responses, and bearer-token failures
- updated README API surface and current status

Limitations:

- RBAC and tenant-context services are not implemented yet; future organisation/project/member routes must add explicit permission checks
- organisation creation and membership management routes are not implemented yet, so `GET /me` only reports memberships already present in persistence
- token validation currently supports user bearer tokens only; API key authentication remains a future ticket
- the committed JWT secret is a local placeholder only and is not suitable for production
- authentication audit events currently use empty metadata to avoid accidental secret or private-data leakage

## Next recommended ticket

Ticket 007.
