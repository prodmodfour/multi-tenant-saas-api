# Architecture

`multi-tenant-saas-api` is a public portfolio implementation of a production-style
SaaS backend. It is intentionally generic: organisations are tenants, users can
belong to many organisations, and every tenant-owned business query is scoped by
organisation membership or by an organisation-scoped API key.

The codebase uses a `src/` layout and keeps clear boundaries between HTTP, API
contracts, business workflows, persistence, and database schema concerns.

## Runtime components

Local runtime components are:

- **FastAPI application**: ASGI app factory at
  `multi_tenant_saas_api.app:create_app`.
- **PostgreSQL**: relational persistence for users, tenants, projects, API keys,
  audit events, and idempotency records.
- **Alembic**: schema migrations under `alembic/`.
- **Prometheus**: local metrics scraping for `/metrics` in Docker Compose.
- **Grafana**: local dashboard provisioning for portfolio observability.

The Docker Compose stack is for local demo use only. It runs migrations before
starting the API container for convenience, but production deployments should use
reviewed release and migration procedures.

## Layering

The intended dependency direction is:

```text
routes -> schemas -> services -> repositories -> database
```

Responsibilities:

| Layer | Responsibility |
| --- | --- |
| Routes | HTTP status mapping, dependency injection, request/response schemas. |
| Schemas | Pydantic validation and public API contracts. |
| Services | Business workflows, RBAC, tenant isolation, transactions, audit writes, metrics. |
| Repositories | SQLAlchemy query construction and persistence access. |
| Database | SQLAlchemy models, session factory, Alembic migrations. |

Route handlers do not issue SQLAlchemy queries, hash passwords, create tokens, or
hash API keys. Automation guardrails in `scripts/check-architecture-boundaries.sh`
catch obvious route-to-persistence violations, while tests exercise the service
and API behaviour.

## Request flow

A typical protected request follows this path:

1. Request ID middleware resolves or creates `X-Request-ID` and binds it to
   structured JSON logs.
2. Metrics middleware records request count and duration using low-cardinality
   route-template labels.
3. FastAPI dependencies create a request-scoped async SQLAlchemy session and the
   appropriate service objects.
4. Authentication dependencies resolve either a user bearer token or, for project
   endpoints only, an active organisation API key.
5. The service layer loads tenant context, checks permissions, calls repository
   methods with explicit tenant scope, records audit events where required, emits
   business metrics, and commits or rolls back the unit of work.
6. The route maps safe service errors to HTTP responses without leaking secrets or
   private implementation details.

## Domain model

Organisations are the tenant boundary.

| Entity | Tenant relationship | Notes |
| --- | --- | --- |
| `users` | Global identity record | Stores email, display name, active flag, and password hash only. |
| `organisations` | Tenant root | Has a globally unique slug and mutable display name. |
| `organisation_memberships` | Joins users to organisations | Stores one role per user per organisation; `(organisation_id, user_id)` is unique. |
| `projects` | Belongs to exactly one organisation | Soft delete is represented by `deleted_at`; default reads exclude deleted rows. |
| `api_keys` | Belongs to exactly one organisation | Stores key prefix and hash only; raw key is never persisted. |
| `audit_events` | Usually organisation-scoped | Auth/system events may have nullable organisation ID. |
| `idempotency_records` | Scoped to principal and optional organisation | Stores request hash plus safe response snapshots. |

Repository methods for tenant-owned data require an organisation scope or a
current-user membership scope. Project lookups combine `organisation_id` and
`project_id` so IDs from other tenants are not accessible.

## Tenant isolation and RBAC

The role model is explicit:

| Role | Permissions |
| --- | --- |
| `owner` | Manage organisation, members, API keys, projects, and audit events. |
| `admin` | Update organisation metadata, manage non-owner members, manage API keys, read/write projects, read audit events. |
| `member` | Read organisation metadata and read/write projects. |
| `viewer` | Read organisation metadata and read projects only. |

RBAC is implemented in service-level tenant context helpers. Business services
must resolve the current principal, load the principal's membership for the
requested organisation, and require a permission before accessing tenant data.
Membership management also protects the invariant that every organisation has at
least one owner: the last owner cannot be removed or downgraded.

Non-members and cross-tenant requests are rejected before tenant-owned rows are
listed. Some fetches intentionally return safe not-found responses when a tenant
resource does not exist in the requested organisation.

## Authentication model

The project implements local demo email/password authentication:

- `POST /auth/register` creates a user and stores only an Argon2id-derived
  password hash.
- `POST /auth/login` returns a short-lived bearer access token signed with the
  configured local demo secret.
- `GET /me` validates the bearer token and returns public user fields plus
  organisation memberships.

This is not a production identity system. The code intentionally omits password
reset, email verification, OAuth, SSO, refresh-token rotation, MFA, and account
lockout workflows.

## API key model

API keys are organisation-scoped machine credentials for project endpoints only.
Owner/admin users can create, list, and revoke API keys. API keys cannot manage
members, create/list/revoke API keys, or read audit events.

Creation returns raw key material exactly once. Persistence stores a non-secret
prefix for operator identification and a deterministic hash for lookup. Revoked
keys are excluded from authentication. API key requests must target the same
organisation that owns the key.

## Audit logging

Audit events are append-only at the API/service layer. Core business operations
record events such as user registration, login, organisation create/update,
member add/change/remove, project create/update/delete, and API key create/revoke.

Audit metadata is deliberately small and secret-safe. The audit service rejects
obvious secret-bearing metadata keys such as password values, bearer tokens, raw
API keys, and key hashes.

## Idempotency

Selected unsafe creation endpoints accept `Idempotency-Key`:

- `POST /orgs`
- `POST /orgs/{organisation_id}/projects`
- `POST /orgs/{organisation_id}/api-keys`

Idempotency records are scoped by principal type, principal ID, method, path,
key, request body hash, and organisation ID where applicable. A replay with the
same body returns the stored response and `Idempotency-Replayed: true`; reusing
the same key with a different body returns `409 Conflict`.

API key creation has safer replay behaviour: the initial response includes
one-time raw key material, but the stored replay body omits raw key material and
returns metadata plus a replay note.

## Observability

The application exposes:

- `GET /healthz` for lightweight liveness.
- `GET /readyz` for PostgreSQL readiness via a minimal database round trip.
- `GET /metrics` for Prometheus text exposition.
- Structured JSON request logs with `X-Request-ID` propagation.

HTTP metrics use route templates rather than raw tenant/resource IDs to avoid
high-cardinality labels. Business counters cover auth attempts, created
organisations/projects/API keys, revoked API keys, audit events, and idempotency
replay/conflict outcomes.

## Known limitations and hardening gaps

This repository demonstrates backend patterns, but it is not production-ready.
Production systems would need at least:

- managed secret storage and rotation;
- TLS termination and reviewed network exposure;
- hardened identity infrastructure, rate limiting, abuse detection, and account
  recovery flows;
- stronger API key lifecycle controls such as scoped permissions, rotation, and
  expiry policies;
- database backups, restore drills, migration rollout procedures, and retention
  policies;
- alerting rules, SLOs, tracing, and log aggregation;
- idempotency record cleanup and stronger concurrency hardening;
- threat modelling, penetration testing, and security review.
