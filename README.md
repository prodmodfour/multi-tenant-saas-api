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

Ticket 000 has bootstrapped the repository skeleton:

- Python 3.12 package using a `src/` layout
- Hatchling build backend
- Ruff, mypy strict mode, pytest, and pytest-cov configuration
- quality gate script
- basic package import test
- documentation and decisions directories

Application endpoints and persistence are intentionally not implemented yet; they will be added by later build tickets.

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

Configuration will use environment variables prefixed with `SAAS_API_`. See `example.env` for public-safe local placeholders.

Do not copy real credentials into committed files. If you create a local `.env`, keep it untracked.

## Documentation

Additional architecture, security, operations, runbook, API walkthrough, and ADR documentation will be added as the corresponding tickets are implemented.
