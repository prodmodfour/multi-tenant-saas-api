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
- Passwords and API keys will be stored only as hashes when those features are implemented.
- Raw API key material should only ever be returned by the intentional one-time create response in the future API key workflow.

## Current status

The project currently includes the repository skeleton and a minimal FastAPI application shell:

- Python 3.12 package using a `src/` layout
- Hatchling build backend
- Ruff, mypy strict mode, pytest, and pytest-cov configuration
- quality gate script
- FastAPI app factory at `multi_tenant_saas_api.app:create_app`
- environment-backed settings using the `SAAS_API_` prefix
- structured JSON logging with request ID context
- `X-Request-ID` propagation
- `GET /healthz` liveness endpoint
- documentation and decisions directories

Persistence, authentication, RBAC, tenant isolation, audit logging, idempotency, metrics, Docker, and CI are intentionally not implemented yet; they will be added by later build tickets.

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

OpenAPI documentation is disabled by default to model a safer production posture. Enable it only for local exploration or explicitly configured demo environments.

Do not copy real credentials into committed files. If you create a local `.env`, keep it untracked.

## Documentation

Additional architecture, security, operations, runbook, API walkthrough, and ADR documentation will be added as the corresponding tickets are implemented.
