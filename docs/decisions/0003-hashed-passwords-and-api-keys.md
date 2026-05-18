# 0003 — Hashed passwords and API keys

## Status

Accepted.

## Context

The project includes local demo authentication and organisation API keys to
show security-aware backend design. Even though this is not a production
identity system, it must model safe handling of passwords, bearer tokens, and
API keys in persisted data, API responses, logs, audit metadata, documentation,
and idempotency records.

The codebase must never persist raw passwords or raw API key material, and raw
API keys should be shown only when they are initially created.

## Decision

Hash passwords before persistence using pwdlib's recommended Argon2id password
hasher. Registration accepts a password only as request input, validates the
configured minimum length, stores only `password_hash`, and returns public user
fields. Login verifies the supplied password against the stored hash and returns
a short-lived bearer access token signed with the configured local demo JWT
secret.

Generate organisation API keys as high-entropy random values. Return the raw
API key only in the intentional one-time create response. Persist only a
non-secret `key_prefix` for identification and a deterministic SHA-256
`key_hash` for lookup. API key list and revoke responses never include raw key
material or key hashes.

Audit metadata, structured logs, public response schemas, and idempotency
response snapshots must reject or avoid obvious secret-bearing fields. API key
creation idempotency snapshots are sanitized so replay responses do not include
the raw key.

## Consequences

A database leak does not directly reveal raw passwords or raw API keys, and API
operators can identify API keys by prefix without being able to recover the
secret. Users must copy and store API keys at creation time because the service
cannot show the raw value again.

The design intentionally keeps local auth simple for portfolio purposes. It does
not replace a hardened production identity provider, password reset flows,
refresh-token rotation, MFA, TLS, secret rotation, rate limiting, alerting, or
managed secret storage. Production systems need those controls before handling
real users or credentials.
