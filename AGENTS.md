# AGENTS.md

You are building `multi-tenant-saas-api`, an independent public portfolio project.

The project demonstrates commercial backend engineering through a production-style multi-tenant SaaS API.

## Portfolio purpose

This repo should make the maintainer look like an obvious backend/platform engineering candidate for product/SaaS/backend roles.

It must demonstrate:

- FastAPI backend API design
- PostgreSQL persistence and migrations
- multi-tenant data modelling
- tenant isolation
- authentication
- role-based access control
- organisation membership management
- hashed password storage
- hashed API key storage
- audit logging
- idempotency keys
- pagination, filtering, and sorting
- structured JSON logging
- request ID propagation
- health/readiness checks
- Prometheus metrics
- Docker Compose local environment
- GitHub Actions CI
- tests, docs, runbooks, and architecture decisions

## Public-safety constraints

This is an independent public portfolio project.

Do not add:

- employer code
- private data
- internal URLs or hostnames
- credentials or tokens
- screenshots of private systems
- non-public architecture
- anything implying employer endorsement

Use only public-safe fake data, local placeholder configuration, and generic demo systems.

## Security boundaries

This is a portfolio implementation, not a production identity system.

However, it must still model good security hygiene:

- Never commit real secrets.
- Never log passwords, password hashes, bearer tokens, API keys, or raw API key material.
- Store password hashes only.
- Store API key hashes only.
- Show raw API keys only once at creation time.
- Use local placeholder secrets only for Docker Compose and tests.
- Make docs explicit that production systems need real secret management, TLS, alerting, backups, and hardened auth.
- Do not create hidden bypass users, backdoors, or special admin bypasses.
- Do not implement arbitrary code execution, shell execution, subprocess command execution, or user-supplied plugin execution.

## Technology direction

Use:

- Python 3.12
- FastAPI
- Pydantic / pydantic-settings
- SQLAlchemy asyncio
- Alembic
- PostgreSQL
- prometheus-client
- uv
- Ruff
- mypy strict mode
- pytest
- Docker Compose
- GitHub Actions

Prefer a `src/` layout.

Optional dependencies are acceptable when justified, for example password hashing and JWT/token support.

## Domain model

Use organisations as tenants.

Suggested core entities:

- users
- organisations
- organisation_memberships
- projects
- api_keys
- audit_events
- idempotency_records

A user can belong to multiple organisations.

An organisation has many members.

A project belongs to exactly one organisation.

API keys belong to exactly one organisation.

Audit events belong to exactly one organisation, except system/auth events where a nullable organisation ID is appropriate.

Idempotency records should be scoped so keys cannot leak behaviour across users, organisations, methods, or paths.

## Role model

Use explicit roles:

```text
owner
admin
member
viewer

Suggested permissions:

owner:
manage organisation
manage members
manage API keys
read/write projects
read audit events
admin:
manage members except owner transfer/removal
manage API keys
read/write projects
read audit events
member:
read/write projects
read limited organisation metadata
viewer:
read projects
read limited organisation metadata

Rules:

Every organisation must always have at least one owner.
A user cannot remove/downgrade the last owner.
Cross-tenant access must be rejected.
Business queries must always be scoped by organisation ID and membership/permission checks.
API direction

System endpoints:

GET /healthz
GET /readyz
GET /metrics

Auth endpoints:

POST /auth/register
POST /auth/login
GET  /me

Organisation endpoints:

POST   /orgs
GET    /orgs
GET    /orgs/{org_id}
PATCH  /orgs/{org_id}
GET    /orgs/{org_id}/members
POST   /orgs/{org_id}/members
PATCH  /orgs/{org_id}/members/{user_id}
DELETE /orgs/{org_id}/members/{user_id}

Project endpoints:

POST   /orgs/{org_id}/projects
GET    /orgs/{org_id}/projects
GET    /orgs/{org_id}/projects/{project_id}
PATCH  /orgs/{org_id}/projects/{project_id}
DELETE /orgs/{org_id}/projects/{project_id}

API key endpoints:

POST   /orgs/{org_id}/api-keys
GET    /orgs/{org_id}/api-keys
DELETE /orgs/{org_id}/api-keys/{api_key_id}

Audit endpoints:

GET /orgs/{org_id}/audit-events
Architecture boundaries

Keep clear layers:

routes -> schemas -> services -> repositories -> database

Rules:

Routes should be thin.
Schemas should validate API input/output.
Services should contain business workflow.
Repositories should own database access.
Auth dependencies should resolve principal/context but not perform business workflows.
No database queries in route functions.
No SQLAlchemy calls in route functions.
No password/token/key hashing in route functions.
No cross-tenant queries without explicit tenant scoping.
Authentication model

Implement local demo authentication:

Email/password registration.
Passwords stored as hashes only.
Login returns a bearer access token.
Token payload should identify the user.
GET /me returns the current user and memberships.

Do not implement email sending, password reset email flows, OAuth, SSO, refresh token rotation, or MFA unless explicitly added in future tickets.

Make docs clear that production systems should usually use hardened identity providers or carefully reviewed auth infrastructure.

API key model

Implement organisation-scoped API keys:

raw key returned only once at creation
key hash persisted
prefix stored for identification
name/label stored
created_at
revoked_at nullable
last_used_at nullable if practical
scopes/role if practical

API key requests should authenticate to the organisation they belong to.

Do not allow API keys to manage members or create other API keys unless explicitly justified. Prefer API keys for project read/write operations and audit-safe machine access.

Audit logging

Record important events:

user registered
user logged in
organisation created
organisation updated
member added
member role changed
member removed
project created
project updated
project deleted
API key created
API key revoked

Audit logs should contain:

ID
organisation ID nullable where appropriate
actor user ID nullable
actor API key ID nullable
action
target type
target ID nullable
metadata JSON
created_at

Do not store secrets, raw tokens, raw API keys, or passwords in audit metadata.

Idempotency

Support idempotency for unsafe creation endpoints where practical.

Use an Idempotency-Key header.

For repeated requests with:

same principal
same method
same path
same idempotency key
same request body hash

return the original result.

For same key but different body hash, return conflict.

At minimum, support idempotency for:

POST /orgs
POST /orgs/{org_id}/projects
POST /orgs/{org_id}/api-keys

Avoid overengineering. The purpose is to demonstrate the pattern safely.

Observability

Implement:

GET /healthz
GET /readyz
GET /metrics
structured JSON logs
request ID propagation with X-Request-ID
Prometheus metrics for:
API requests
request duration
auth attempts
organisations created
projects created
API keys created/revoked
audit events recorded
idempotency replays/conflicts
Configuration

Use environment variables with the prefix:

SAAS_API_

Examples:

SAAS_API_APP_NAME
SAAS_API_APP_VERSION
SAAS_API_ENVIRONMENT
SAAS_API_LOG_LEVEL
SAAS_API_DOCS_ENABLED
SAAS_API_DATABASE_URL
SAAS_API_JWT_SECRET
SAAS_API_JWT_ISSUER
SAAS_API_ACCESS_TOKEN_TTL_SECONDS
SAAS_API_PASSWORD_MIN_LENGTH

Docs/OpenAPI should be disabled by default unless explicitly enabled for local exploration.

Testing expectations

Every meaningful ticket should add or update tests.

Test:

registration
login
password hash is not raw password
current user endpoint
organisation creation
membership creation
RBAC allowed/denied cases
last-owner protection
tenant isolation
project CRUD
pagination/filtering/sorting
API key creation/revocation
API key cannot see other tenant data
audit event creation
idempotency replay
idempotency conflict
readiness checks
metrics endpoint
docs disabled by default
no secret leakage in responses
Documentation expectations

Maintain:

README.md
docs/architecture.md
docs/api-walkthrough.md
docs/operations.md
docs/runbook.md
docs/security.md
docs/decisions/

Include at least these ADRs:

docs/decisions/0001-organisations-as-tenants.md
docs/decisions/0002-role-based-access-control.md
docs/decisions/0003-hashed-passwords-and-api-keys.md
docs/decisions/0004-idempotency-records.md
docs/decisions/0005-append-only-audit-events.md

Each ADR should include:

status
context
decision
consequences
Automation behaviour

When invoked by the build loop:

Read AGENTS.md, BUILD_TICKETS.md, and BUILD_NOTES.md.
Select the lowest-numbered TODO or IN_PROGRESS ticket.
Implement only that ticket.
Do not start future tickets.
Do not broaden scope.
Add/update tests.
Add/update docs if behaviour, setup, architecture, operations, security, or limitations change.
Run scripts/quality-gate.sh.
Update BUILD_TICKETS.md.
Update BUILD_NOTES.md.
Commit the completed ticket with a conventional commit message.
Leave the working tree clean.

If blocked:

explain the blocker in BUILD_NOTES.md
mark the ticket BLOCKED if appropriate
do not mark it DONE
do not commit broken partial work
leave the working tree clean if possible
Commit style

Use conventional commits:

chore:
feat:
fix:
test:
docs:
refactor:
ci:

Examples:

feat: add organisation-scoped project API
test: cover tenant isolation
docs: add RBAC architecture decision
ci: add quality gate workflow
