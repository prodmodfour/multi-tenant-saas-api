# 0002 — Role-based access control

## Status

Accepted.

## Context

The API needs tenant-specific authorization rather than a single global user
role. A user may be an owner in one organisation, a viewer in another, and a
non-member elsewhere. Membership management also needs to preserve the invariant
that each organisation always has at least one owner.

The project should demonstrate explicit RBAC while staying small enough for a
portfolio codebase and avoiding hidden bypass users or special administrator
backdoors.

## Decision

Use four explicit organisation roles: `owner`, `admin`, `member`, and `viewer`.
Map those roles to service-level permissions in the domain layer:

- `owner`: all organisation permissions, including managing the organisation,
  members, API keys, projects, and audit events.
- `admin`: update organisation metadata, manage API keys, read/write projects,
  read audit events, and manage non-owner memberships.
- `member`: read organisation metadata and read/write projects.
- `viewer`: read organisation metadata and read projects only.

Service workflows must resolve a tenant context from the current principal,
organisation, membership, role, and required permission before they touch
business data. Owner-sensitive membership operations are handled as explicit
business rules: admins cannot grant, change, or remove owner memberships, and no
workflow may remove or downgrade the last owner.

API keys are not organisation members and do not receive member-management or
API-key-management permissions. They are resolved as organisation-scoped machine
principals for project read/write endpoints only.

## Consequences

The permission mapping is central, testable, and easy to describe in API docs.
Tenant authorization decisions live in services instead of routes, which keeps
HTTP handlers thin and preserves the documented layer boundary:

```text
routes -> schemas -> services -> repositories -> database
```

The model deliberately does not support custom roles, per-resource ACLs, deny
rules, owner transfer workflows, or fine-grained API key scopes yet. Future
requirements can extend the permission enum or add scoped grants, but they must
keep last-owner protection and cross-tenant denial explicit.
