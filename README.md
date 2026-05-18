# Multi-Tenant SaaS API

`multi-tenant-saas-api` is an independent public portfolio project that will grow into a production-style FastAPI backend for a multi-tenant SaaS product.

The project is intentionally generic and public-safe. It is not based on employer code, private systems, internal URLs, credentials, screenshots, or non-public architecture.

## Portfolio goals

This repository is designed to demonstrate commercial backend/platform engineering skills, including:

- FastAPI API design
- PostgreSQL persistence and migrations
- multi-tenant data modelling and tenant isolation
- authentication and role-based access control
- organisation membership management
- hashed password and API key storage
- audit logging and idempotency keys
- pagination, filtering, and sorting
- structured JSON logging and request ID propagation
- health/readiness checks and Prometheus metrics
- Docker Compose local infrastructure
- GitHub Actions CI, tests, documentation, runbooks, and ADRs

## Security and public-safety boundaries

This is a portfolio implementation, not a production identity or security baseline.

- Do not commit real secrets, credentials, private data, or employer-specific material.
- Use only local placeholder values in examples and local development files.
- Production deployments would require real secret management, TLS, hardened authentication, alerting, backups, and operational review.
- Password hashing utilities store only derived hashes; API keys will be stored only as hashes when that workflow is implemented.
- Raw API key material should only ever be returned by the intentional one-time create response in the future API key workflow.

## Current status

The project currently includes the repository skeleton, a minimal FastAPI application shell, and the first persistence layer contracts:

- Python 3.12 package using a `src/` layout
- Hatchling build backend
- Ruff, mypy strict mode, pytest, and pytest-cov configuration
- quality gate script
- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix
- structured JSON logging with request ID context
- `X-Request-ID` propagation
- `GET /healthz` liveness endpoint
- domain identifiers, organisation roles, permission mapping, project statuses, and audit actions
- Pydantic request/response schemas for the planned auth, organisation, membership, project, API key, audit, and pagination contracts
- async SQLAlchemy engine/session helpers
- SQLAlchemy models for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- Alembic configuration and an initial PostgreSQL migration
- repository classes for users, organisations, memberships, projects, API keys, audit events, and idempotency records
- tenant-scoped repository methods for organisation membership lists, project access, API key management, audit event reads, and idempotency lookups
- password policy checks plus Argon2id password hashing and verification utilities
- signed bearer access token creation/validation utilities and a typed authenticated principal model
- request-scoped database session dependency wiring for API workflows
- auth service workflows and routes for registration, login, and current-user lookup
- `POST /auth/register`, `POST /auth/login`, and `GET /me`
- successful registration/login audit event writes with secret-safe metadata
- documentation and decisions directories

RBAC enforcement, tenant isolation for organisation/project APIs, broader audit integration, idempotency replay behaviour, readiness checks, metrics, Docker, and CI are intentionally not implemented yet; they will be added by later build tickets.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) for dependency management

## Local setup

```bash
uv sync --all-groups
uv run pytest
```

Run the full local quality gate:

```bash
scripts/quality-gate.sh
```

Common shortcuts are available through `make`:

```bash
make install
make lint
make test
make quality
```

## Configuration

Configuration uses environment variables prefixed with `SAAS_API_`. See `example.env` for public-safe local placeholders.

| Variable | Default | Description |
| --- | --- | --- |
| `SAAS_API_APP_NAME` | `multi-tenant-saas-api` | Application name used in FastAPI metadata and health responses. |
| `SAAS_API_APP_VERSION` | `0.1.0` | Application version used in FastAPI metadata and health responses. |
| `SAAS_API_ENVIRONMENT` | `local` | Environment label included in health responses and future logs/metrics. |
| `SAAS_API_LOG_LEVEL` | `INFO` | Structured JSON logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`). |
| `SAAS_API_DOCS_ENABLED` | `false` | Enables `/docs`, `/redoc`, and `/openapi.json` for local exploration when set to `true`. |
| `SAAS_API_DATABASE_URL` | `postgresql+asyncpg://saas_api:saas_api@localhost:5432/saas_api` | Async SQLAlchemy PostgreSQL URL used by the application and Alembic migrations. The default is a local placeholder only. |
| `SAAS_API_JWT_SECRET` | `local-placeholder-jwt-secret-not-for-production` | Local placeholder signing secret for demo bearer access tokens. Production systems require managed secrets and rotation. |
| `SAAS_API_JWT_ISSUER` | `multi-tenant-saas-api-local` | Issuer claim used when creating and validating bearer access tokens. |
| `SAAS_API_ACCESS_TOKEN_TTL_SECONDS` | `900` | Lifetime for local demo bearer access tokens. |
| `SAAS_API_PASSWORD_MIN_LENGTH` | `12` | Minimum password length enforced by the password policy utility before hashing. |

OpenAPI documentation is disabled by default to model a safer production posture. Enable it only for local exploration or explicitly configured demo environments.

Do not copy real credentials into committed files. If you create a local `.env`, keep it untracked.

## Implemented API surface

System endpoints:

- `GET /healthz` — liveness check with application metadata.

Auth endpoints:

- `POST /auth/register` — creates a local demo user, stores only an Argon2id-derived password hash, rejects duplicate email addresses, and returns public user fields.
- `POST /auth/login` — validates local email/password credentials and returns a short-lived bearer access token with generic failure behaviour for unknown email or wrong password.
- `GET /me` — requires `Authorization: Bearer <token>` and returns the current active user plus organisation membership summaries.

Password hashes and raw passwords are never returned by these endpoints. Registration and successful login create nullable-organisation audit events with empty, secret-safe metadata.

## Domain, schema, and persistence contracts

The current domain layer defines organisation roles (`owner`, `admin`, `member`, `viewer`), service-level permissions, project statuses, and audit action names. The Pydantic schemas define the API data contracts, while service workflows own registration, login, and current-user business logic for the implemented auth endpoints.

Password fields use secret-safe request types, response schemas do not include password hashes, and API key metadata schemas do not include raw keys or key hashes. The password utility enforces a configurable local policy and hashes new passwords with pwdlib's recommended Argon2id hasher before persistence. The bearer-token utility signs short-lived local demo access tokens and validates them into an authenticated user principal for `GET /me`. Production systems need real secret management, TLS, token/key rotation, monitoring, and hardened identity review.

The database model stores `password_hash` and `key_hash` fields only; raw API key material is represented only by the intentional one-time API key creation response schema.

Repository classes live under `multi_tenant_saas_api.repositories` and own SQLAlchemy statement construction for business persistence operations. Future service and route layers should call these repositories rather than querying ORM models directly. Repository methods that access tenant-owned business data require an organisation scope or a user-membership scope where applicable; RBAC decisions remain a future service-layer responsibility.

The initial PostgreSQL schema is managed by Alembic:

```bash
uv run alembic upgrade head
```

A local PostgreSQL service is not included until the Docker Compose ticket, so the migration command requires a separately available database or a future Compose stack.

## Documentation

Additional architecture, security, operations, runbook, API walkthrough, and ADR documentation will be added as the corresponding tickets are implemented.
