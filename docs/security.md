# Security model

This project models good security hygiene for a public portfolio SaaS API, while
remaining explicit that it is not a production identity or security baseline.
Do not commit real credentials, private data, employer-specific terms, internal
hostnames, or screenshots of private systems.

## Public-safety boundary

Repository examples use public-safe placeholder values only. The local Docker
Compose stack, `example.env`, and documentation are safe for portfolio review and
are not suitable for production deployment.

Automation guardrails check for common mistakes:

- committed `.env` files other than `example.env`;
- real-looking high-confidence secret patterns;
- internal-looking hostnames;
- locally configured forbidden private terms;
- non-placeholder sensitive values in sample files;
- secret-looking fields on public response schemas.

Guardrails are heuristic and complement, rather than replace, security review and
secret scanning.

## Authentication

The application implements local demo email/password authentication:

- Registration accepts email, display name, and password.
- Password policy enforces a configurable minimum length through
  `SAAS_API_PASSWORD_MIN_LENGTH`.
- Passwords are hashed before persistence with pwdlib's recommended Argon2id
  hasher.
- Login returns a short-lived bearer access token.
- Bearer tokens identify the user and are validated before protected user routes.

Password hashes are never returned in API responses and should never be logged.
Login failure responses are intentionally generic so the API does not distinguish
unknown email from wrong password for callers.

Production systems should normally use a hardened identity provider or a deeply
reviewed in-house identity service. This demo intentionally does not implement
email verification, password reset, OAuth, SSO, refresh-token rotation, MFA,
account lockout, or device/session management.

## Token handling

Bearer access tokens are signed with `SAAS_API_JWT_SECRET` and include a finite
TTL from `SAAS_API_ACCESS_TOKEN_TTL_SECONDS`. The committed defaults are local
placeholders only.

Operational rules:

- Do not log bearer tokens.
- Do not place bearer tokens in documentation, screenshots, or issue reports.
- Use `Authorization: Bearer <access-token>` only as a placeholder in examples.
- Rotate and store real production signing secrets in managed secret storage.

The current implementation does not provide token revocation lists, refresh-token
rotation, or step-up authentication.

## API key handling

API keys are organisation-scoped machine credentials for project endpoints.
Owner/admin users can create, list, and revoke keys.

Security properties:

- Raw key material is returned only by the initial create response.
- The database stores only a key hash and a short non-secret prefix.
- API key list and revoke responses expose metadata only.
- Revoked keys cannot authenticate.
- API keys are accepted only on project endpoints.
- API keys cannot manage members, create/list/revoke API keys, or read audit
  events.
- API keys cannot access projects from another organisation.

API key creation idempotency intentionally does not replay raw key material. A
replay returns metadata plus a replay note so a caller cannot recover the raw key
from stored response snapshots.

Production hardening should add key expiry, rotation workflows, finer-grained
scopes, per-key rate limits, alerting on suspicious use, and stronger lifecycle
management.

## Tenant isolation and RBAC

Organisations are tenants. User access to tenant data requires an organisation
membership and a role with the required permission.

Roles:

| Role | Summary |
| --- | --- |
| `owner` | Full organisation administration, including members, API keys, projects, and audit events. |
| `admin` | Administration except owner grant/change/removal; can manage API keys, projects, and audit events. |
| `member` | Read organisation metadata and read/write projects. |
| `viewer` | Read organisation metadata and projects only. |

Every tenant-owned business workflow performs service-layer permission checks
before accessing data. Repository methods scope tenant-owned queries by
`organisation_id` where appropriate. Membership workflows protect the last-owner
invariant so every organisation keeps at least one owner.

## Audit logging

Audit events record security- and business-relevant operations:

- user registered;
- user logged in;
- organisation created or updated;
- member added, role changed, or removed;
- project created, updated, or deleted;
- API key created or revoked.

Audit metadata must not contain passwords, password hashes, bearer tokens, raw API
keys, key hashes, authorization values, or other secrets. The audit service
rejects obvious secret-bearing metadata field names. Audit events are append-only
at the API/service layer and can be read by owner/admin users only.

## Idempotency safety

`Idempotency-Key` is supported for selected creation endpoints. Records are scoped
by principal, method, path, optional organisation ID, and request body hash. This
prevents a key from replaying behaviour across users, API keys, tenants,
endpoints, or request bodies.

Reusing a key with a different request body returns `409 Conflict` and does not
expose body hashes. Response snapshots reject obvious secret-bearing fields; API
key creation snapshots omit raw key material.

Current limitations include no background cleanup job for old records and limited
concurrency hardening beyond database uniqueness constraints.

## Logging and observability

Structured JSON logs include request metadata and `X-Request-ID` but must not
include passwords, password hashes, bearer tokens, raw API keys, or API key
hashes. Metrics labels use route templates rather than tenant/resource IDs to
avoid high-cardinality labels and unnecessary tenant data exposure.

`GET /metrics` is unauthenticated for local Prometheus scraping. In production,
metrics should be protected by network controls or an authenticated observability
path.

## Configuration and docs exposure

All application settings use the `SAAS_API_` prefix. OpenAPI docs are disabled by
default (`SAAS_API_DOCS_ENABLED=false`) and enabled only for local exploration in
Docker Compose.

Do not commit real settings files. Local untracked `.env` files should stay out
of version control. The default database URL, JWT secret, and Compose credentials
are placeholders only.

## Production-hardening gaps

Before using this design for real customers, add or review:

- managed secrets, rotation, and incident response for leaked credentials;
- TLS everywhere and hardened network boundaries;
- mature identity provider integration or a reviewed auth platform;
- rate limiting, brute-force protection, and abuse monitoring;
- token revocation and session management;
- API key expiry, rotation, scopes, and audit alerts;
- database encryption strategy, backups, restores, and disaster recovery;
- vulnerability scanning, dependency update policy, and container hardening;
- centralised logs, alerting, SLOs, traces, and retention policies;
- formal threat modelling and security review.
