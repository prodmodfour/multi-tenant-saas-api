# BUILD_NOTES.md

## Current state

Tickets 000 and 001 are complete. The repository now has the initial Python 3.12 `src/` layout, packaging configuration, documentation placeholders, local placeholder configuration, a Makefile, a basic import test, and a minimal FastAPI application shell.

Implemented application behaviour currently includes:

- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix
- docs/OpenAPI disabled by default and explicitly enableable with `SAAS_API_DOCS_ENABLED=true`
- structured JSON logging configuration
- `X-Request-ID` propagation and request-scoped log context
- `GET /healthz`

Persistence, authentication, RBAC, tenant isolation, audit logging, idempotency, metrics, Docker, and CI are not implemented yet.

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

Implemented Ticket 001:

- added FastAPI and pydantic-settings dependencies, plus httpx for API tests
- added app factory and ASGI entrypoint
- added settings loaded from `SAAS_API_` environment variables
- disabled `/docs`, `/redoc`, and `/openapi.json` by default
- added structured JSON logging setup with request ID context
- added request middleware that propagates valid inbound `X-Request-ID` values or generates one when absent
- added `GET /healthz` with application name, version, environment, and status
- added API tests for health, request ID propagation, docs disabled by default, docs enabled when configured, and environment-backed settings
- updated README configuration documentation

Limitations:

- no database, readiness check, metrics, authentication, RBAC, tenant isolation, business APIs, audit logging, or idempotency support yet
- structured request logs intentionally include method, path, status code, duration, and request ID only; request/response bodies and authentication material are not logged

## Next recommended ticket

Ticket 002.
