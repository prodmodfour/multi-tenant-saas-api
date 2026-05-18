# Runbook

This runbook is for local demo operation and portfolio review. It favours safe,
repeatable checks and avoids exposing secrets.

## First principles

- Do not paste real passwords, bearer tokens, raw API keys, database URLs, or
  private hostnames into logs, tickets, screenshots, or committed files.
- Use `X-Request-ID` to correlate client failures with API logs.
- Prefer `/readyz` for dependency health and `/healthz` for process liveness.
- Treat Docker Compose data as disposable local demo state.
- Run `scripts/quality-gate.sh` before considering a change complete.

## Quick checks

```bash
curl -fsS http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
curl -fsS http://localhost:8000/metrics
docker compose ps
docker compose logs api
```

If using a protected API endpoint, use placeholders in notes:

```http
Authorization: Bearer <access-token>
X-Request-ID: <request-id>
```

## API container does not start

Symptoms:

- `docker compose up --build` exits or restarts the `api` service.
- `GET /healthz` fails to connect.

Checks:

```bash
docker compose ps
docker compose logs api
docker compose logs postgres
```

Likely causes and actions:

- PostgreSQL is not healthy: inspect `postgres` logs and health status.
- Migration failed: run `uv run alembic upgrade head` locally against the same
  safe local database URL and inspect the error.
- Dependency installation/image build failed: rebuild with `docker compose build
  --no-cache api` if a cached layer is suspected.
- Port already in use: stop the conflicting local process or change local port
  mapping in an uncommitted override.

## Readiness returns 503

Symptoms:

- `/healthz` returns `200`, but `/readyz` returns `503` with
  `status: "not_ready"`.

Checks:

```bash
docker compose ps postgres
docker compose logs postgres
docker compose exec postgres pg_isready -U saas_api -d saas_api
```

Actions:

- Confirm PostgreSQL is running and healthy.
- Confirm `SAAS_API_DATABASE_URL` points to the intended local database.
- Apply migrations with `uv run alembic upgrade head` if schema setup is missing.
- Restart the local stack after correcting configuration.

Do not include database credentials or connection strings from non-local systems
in issue reports.

## Alembic migration fails

Symptoms:

- API startup fails before Uvicorn begins serving.
- CI migration step fails.

Checks:

```bash
uv run alembic current
uv run alembic upgrade head
```

Actions:

- Verify PostgreSQL is reachable and uses a safe local/test URL.
- Inspect the migration error for schema drift or invalid SQL.
- Re-run `scripts/quality-gate.sh` after fixing the migration.
- Do not mark the build ticket complete until migrations and tests pass.

## Authentication failures

Symptoms:

- `POST /auth/login` returns `401`.
- Protected endpoints return `401`.

Checks:

- Confirm the user was registered in the same local database.
- Confirm the password used in the local demo is correct without writing it to
  logs or committed files.
- Confirm the bearer token has not expired.
- Confirm the request uses `Authorization: Bearer <access-token>` format.
- Confirm `SAAS_API_JWT_SECRET` and `SAAS_API_JWT_ISSUER` are consistent between
  token creation and validation.

Actions:

- Login again to get a fresh access token.
- Restart only after checking whether local configuration changed.
- Do not paste token contents into notes.

## Permission or tenant access denied

Symptoms:

- Tenant routes return `403 Forbidden`.
- Tenant-scoped resources return `404 Not Found` in a cross-tenant scenario.

Checks:

- Call `GET /me` to confirm the user has the expected organisation membership.
- Verify the route organisation ID matches the intended tenant.
- Check the user's role and required permission:
  - owner/admin can manage members and API keys;
  - member can read/write projects;
  - viewer can read projects only;
  - owner/admin can read audit events.
- For API key requests, verify the key belongs to the same organisation and the
  endpoint is a project endpoint.

Actions:

- Adjust membership through an owner/admin user if appropriate.
- Use a user bearer token, not an API key, for member, API key, or audit routes.
- Treat cross-tenant denial as expected protective behaviour unless tests prove a
  regression.

## Last-owner protection conflict

Symptoms:

- Membership role update or removal returns `409 Conflict` with the last-owner
  invariant message.

Actions:

- Add or promote another owner first.
- Retry the downgrade or removal only after another owner exists.
- Do not bypass this invariant in data fixes.

## Idempotency conflict

Symptoms:

- A creation endpoint with `Idempotency-Key` returns `409 Conflict`.

Likely cause:

- The same principal reused the same key, method, path, and organisation scope
  with a different request body.

Actions:

- Retry the exact original request body if the goal is replay.
- Use a new idempotency key for a different operation.
- Do not expose request hashes in logs or client responses.

## API key authentication fails

Symptoms:

- Project endpoint returns `401` for an API key.
- Project endpoint returns `403` when using a key from another organisation.

Checks:

- Confirm the raw key was copied from the one-time create response at creation
  time; it cannot be recovered from list responses.
- Confirm the key has not been revoked.
- Confirm the route organisation matches the key's organisation.
- Confirm the request targets a project endpoint.

Actions:

- Create a new key if the raw key was lost.
- Revoke unused or exposed keys.
- Use a user bearer token for API key management routes.

## Audit events appear missing

Symptoms:

- `GET /orgs/{organisation_id}/audit-events` returns an empty or unexpected page.

Checks:

- Confirm the caller is owner/admin for that organisation.
- Confirm the business operation completed successfully.
- Check `limit` and `offset`; audit events are returned newest-first.
- Confirm the route organisation ID is correct.

Actions:

- Reproduce the business operation locally and inspect the audit endpoint.
- Run the audit API tests if a regression is suspected.

## Metrics or dashboards are unavailable

Symptoms:

- `/metrics` fails.
- Prometheus target is down.
- Grafana dashboard has no data.

Checks:

```bash
curl -fsS http://localhost:8000/metrics
docker compose ps prometheus grafana
docker compose logs prometheus
docker compose logs grafana
```

Actions:

- Confirm the API service is healthy.
- In Prometheus, inspect <http://localhost:9090/targets>.
- Confirm the Compose network target is `api:8000/metrics`.
- Restart Prometheus/Grafana after configuration changes.

## Quality gate or CI fails

Checks:

```bash
scripts/quality-gate.sh
```

Actions:

- Fix failures in the order reported.
- For guardrail failures, remove risky content or replace it with obvious
  placeholders such as `<access-token>` or `local-placeholder-value`.
- For architecture guardrail failures, move persistence, hashing, and token work
  out of route modules and into services/repositories.
- For mypy/Ruff/test failures, make the smallest change that resolves the
  current ticket only.

## Suspected secret exposure

If a real secret, raw token, raw API key, private URL, or employer-specific term
is accidentally committed or displayed:

1. Stop sharing the branch or artifact.
2. Rotate or revoke the exposed credential in the real system if it was real.
3. Remove the material from the repository and documentation.
4. Re-run public-safety and secret-leakage guardrails.
5. Record what happened in project notes without repeating the secret.

Never rely on deleting a line from the latest commit as the only remediation for a
real exposed credential; assume it must be rotated.
