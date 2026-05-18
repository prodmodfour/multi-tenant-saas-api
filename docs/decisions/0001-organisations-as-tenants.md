# 0001 — Organisations as tenants

## Status

Accepted.

## Context

The API is a public portfolio implementation of a multi-tenant SaaS backend.
It needs a clear tenant boundary that is easy to explain, test, and enforce
across projects, API keys, audit events, and idempotency records.

Users can belong to more than one customer-like workspace. Tenant-owned data
must not be readable or mutable across workspaces, and business queries must
have an explicit tenant scope rather than relying on caller-supplied resource
IDs alone.

## Decision

Use `organisations` as the tenant root.

Each organisation has its own stable UUID primary key and a globally unique
slug. Tenant-owned entities reference the organisation ID:

- `organisation_memberships` join users to organisations and store the user's
  role in that tenant.
- `projects` belong to exactly one organisation and are always queried with an
  organisation scope.
- `api_keys` belong to exactly one organisation and can authenticate only to
  project endpoints for that organisation.
- `audit_events` usually belong to one organisation; system/auth events may use
  a nullable organisation ID.
- `idempotency_records` include the organisation ID where a request is
  organisation-scoped, and keep it nullable for global user actions such as
  organisation creation.

Service workflows must resolve the caller's tenant context before reading or
mutating tenant-owned data. Repository methods for tenant-owned rows must accept
an organisation scope or an equivalent membership-scoped query. Project lookups
combine `organisation_id` and `project_id` so a resource ID from another tenant
is not sufficient to access data.

## Consequences

This keeps tenant isolation visible in the data model, service layer, and tests.
A user can participate in many organisations without duplicating identity
records, while each organisation can independently manage members, projects,
API keys, and audit history.

The trade-off is that every future tenant-owned table and repository method must
carry organisation scoping intentionally. Forgetting that scope is a security
bug, so architecture guardrails and tests should continue to check route,
service, and repository boundaries. Production systems might add database row
level security, tenant partitioning, or dedicated deployment topologies, but
this portfolio implementation keeps a single shared schema for clarity.
