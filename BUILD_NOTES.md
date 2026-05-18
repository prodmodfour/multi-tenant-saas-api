# BUILD_NOTES.md

## Current state

Tickets 000, 001, and 002 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, a minimal FastAPI application shell, and the first domain/schema contracts.

Implemented application behaviour currently includes:

- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix
- docs/OpenAPI disabled by default and explicitly enableable with `SAAS_API_DOCS_ENABLED=true`
- structured JSON logging configuration
- `X-Request-ID` propagation and request-scoped log context
- `GET /healthz`

Implemented domain/schema contracts currently include:

- typed domain identifiers for users, organisations, memberships, projects, API keys, and audit events
- organisation roles (`owner`, `admin`, `member`, `viewer`) and immutable permission mapping helpers
- project statuses and audit action enums
- Pydantic schemas for planned auth, current-user, organisation, membership, project, API key, audit event, and pagination API contracts
- secret-safe request schemas for passwords and response schemas that omit password hashes, API key hashes, and raw API key material except the intentional one-time API key creation response schema

Persistence, authentication workflows, RBAC enforcement, tenant isolation, audit logging integration, idempotency, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 002:

- added `multi_tenant_saas_api.domain` with typed ID definitions, organisation roles, permissions, role-to-permission mapping helpers, project statuses, and audit actions
- added Pydantic schemas for registration, login, current user, organisations, memberships, projects, API keys, audit events, and pagination metadata
- used `SecretStr` for password request fields and added email validation support through the public `email-validator` dependency
- kept password hashes and API key hashes out of response schemas; raw API key material appears only in the one-time API key creation response schema
- added tests for role validation, permission mapping, schema validation, invalid emails, short passwords, invalid project statuses, invalid roles, invalid slugs, pagination metadata bounds, and secret-field exclusions
- updated README current-status and domain/schema contract documentation

Limitations:

- schemas define planned API contracts only; backing persistence, services, repositories, authentication utilities, and routes are not implemented yet
- password policy enforcement is still schema-level minimum-length validation only; the dedicated password hashing and policy service is planned for Ticket 005
- RBAC is represented by permission mapping helpers only; tenant context and enforcement are planned for Ticket 007 and later business API tickets

## Next recommended ticket

Ticket 003.
