# 0004 — Idempotency records

## Status

Accepted.

## Context

Clients may retry unsafe creation requests after timeouts or network failures.
Without idempotency support, a retry could create duplicate organisations,
projects, or API keys. The API also needs to prevent idempotency keys from
leaking behaviour across users, API keys, tenants, methods, paths, or request
bodies.

API key creation has an additional constraint: the raw key is returned only once
and must not be stored in a replay snapshot.

## Decision

Support optional `Idempotency-Key` headers on selected creation endpoints:

- `POST /orgs`
- `POST /orgs/{org_id}/projects`
- `POST /orgs/{org_id}/api-keys`

Persist an `idempotency_records` row for a completed idempotent request. Each
record stores the principal type, principal ID, nullable organisation ID, key,
HTTP method, path, deterministic request body hash, response status code,
secret-safe response body, creation timestamp, and optional expiry timestamp.

When a matching record is found with the same body hash, return the stored
response with `Idempotency-Replayed: true`. When the same scoped key is reused
with a different body hash, return a conflict without exposing either hash.
Organisation-scoped replays still perform current tenant permission checks
before returning stored data.

For API key creation, store a sanitized response snapshot that omits `raw_key`
and adds a replay note explaining that raw key material is not replayed.

## Consequences

Retries for supported create endpoints can be safe and predictable while keeping
idempotency behaviour isolated by principal, route, method, tenant, and body.
The stored response body makes successful replays straightforward, but it also
means snapshot filtering must remain strict so credentials are not persisted.

The current implementation does not include background cleanup, expiry
enforcement, pessimistic locking, or advanced duplicate-request concurrency
handling. Those concerns are called out as production-hardening work. Future
endpoints can opt in to the same service pattern when their response snapshots
can be made secret-safe.
