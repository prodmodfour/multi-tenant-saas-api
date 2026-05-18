# 0005 — Append-only audit events

## Status

Accepted.

## Context

A multi-tenant SaaS API should leave an operator-readable trail of important
security and business actions. The project needs to demonstrate audit logging
for authentication, organisation management, membership changes, project
changes, and API key lifecycle events without storing passwords, tokens, raw API
keys, or other private authentication material in audit metadata.

Audit history must be tenant-scoped where possible and must not be mutable
through public API workflows.

## Decision

Use an append-only audit service for business event creation. The service
records events with these fields:

- audit event ID
- nullable organisation ID
- nullable actor user ID
- nullable actor API key ID
- action
- target type
- nullable target ID
- metadata JSON
- creation timestamp

Organisation-scoped business events store the organisation ID. Auth/system
style events such as registration and login may use a nullable organisation ID.
The service validates metadata recursively and rejects obvious secret-bearing key
names before writing the event.

Business services call the audit service inside their existing unit of work so
important domain writes and their audit events commit or roll back together. The
public API exposes only tenant-scoped audit reads through the
`GET /orgs/{org_id}/audit-events` endpoint, protected by the
`read_audit_events` permission.

There is no public audit update or delete workflow.

## Consequences

Core workflows produce a consistent audit trail that is scoped by organisation
and safe to expose to authorised owner/admin users. The append-only service
boundary makes mutation of audit history an explicit non-feature at the API and
service layer.

The audit log is not cryptographically tamper-evident and does not yet include
retention policies, export pipelines, archival storage, partitioning, or alerting
rules. Production systems would need those controls, along with reviewed access
policies and operational monitoring, before relying on the log for compliance or
incident response.
