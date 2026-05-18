# Documentation

Project documentation for the implemented API is organised by topic:

- [Architecture](architecture.md)
- [Security model](security.md)
- [API walkthrough](api-walkthrough.md)
- [Operations guide](operations.md)
- [Runbook](runbook.md)

Architecture decision records are tracked under `docs/decisions/`:

- [0001 — Organisations as tenants](decisions/0001-organisations-as-tenants.md)
- [0002 — Role-based access control](decisions/0002-role-based-access-control.md)
- [0003 — Hashed passwords and API keys](decisions/0003-hashed-passwords-and-api-keys.md)
- [0004 — Idempotency records](decisions/0004-idempotency-records.md)
- [0005 — Append-only audit events](decisions/0005-append-only-audit-events.md)

## Continuous integration

GitHub Actions CI is defined in `.github/workflows/ci.yml`. The workflow uses Python 3.12, uv, and a PostgreSQL service container. It runs shell syntax checks, automation guardrails, dependency sync from `uv.lock`, Ruff linting and format checks, mypy, Docker Compose config validation, Alembic migration upgrade, and pytest with coverage.

Implemented guardrails live under `scripts/` and are also part of `scripts/quality-gate.sh`:

- `check-public-safety.sh` scans tracked/non-ignored files for committed `.env` files, real-looking secrets, internal-looking hostnames, sample-file secret values, and locally supplied forbidden terms from `SAAS_API_FORBIDDEN_TERMS_FILE`.
- `check-architecture-boundaries.sh` rejects obvious route-layer imports or calls that cross directly into SQLAlchemy/database/repository concerns.
- `check-secret-leakage.sh` rejects secret-looking fields on public response schema classes except the documented login token and one-time API key creation response.

## Local Docker Compose stack

The repository includes a local-only Docker Compose stack for demo exploration. It starts:

- `api`: the FastAPI app image built from the repository Dockerfile, running as a non-root runtime user.
- `postgres`: local PostgreSQL with public-safe placeholder credentials.
- `prometheus`: a Prometheus container that scrapes the API metrics endpoint through the Compose network.
- `grafana`: a Grafana container with a provisioned Prometheus datasource and a basic API dashboard.

The API service waits for PostgreSQL, runs `alembic upgrade head`, and then starts Uvicorn. The Dockerfile includes a `/healthz` container health check. These settings are only for local portfolio demos; production deployments need real secret management, TLS, hardened runtime policies, backups, and alerting.

Run the stack with:

```bash
docker compose up --build
```

## Role model

Organisations are the tenant boundary. User-driven tenant-scoped business services must resolve the current authenticated principal, load the principal's organisation membership, and enforce role permissions before reading or mutating tenant-owned data. Project services additionally accept active organisation-scoped API keys and require the key's organisation to match the route tenant.

Roles:

- `owner`: manage organisation, manage members, manage API keys, read/write projects, read audit events.
- `admin`: update organisation metadata, manage members except granting/changing/removing owner memberships, manage API keys, read/write projects, read audit events.
- `member`: read organisation metadata and read/write projects.
- `viewer`: read organisation metadata and read projects only.

Every organisation must retain at least one owner. The membership management workflow uses RBAC last-owner protection so member updates cannot remove or downgrade the final owner.

## Organisation API

Implemented organisation endpoints:

- `POST /orgs`: creates an organisation for the current bearer-token user, derives a slug from the name when omitted, enforces unique slugs, makes the creator an `owner`, and writes an `organisation.created` audit event with secret-safe metadata.
- `GET /orgs`: lists only organisations where the current user has a membership and returns `limit`/`offset` pagination metadata.
- `GET /orgs/{org_id}`: requires tenant membership and `read_organisation` permission.
- `PATCH /orgs/{org_id}`: requires tenant membership and `update_organisation` permission, so `owner` and `admin` can update metadata while `member` and `viewer` are denied.

Organisation names are not globally unique; slugs are the unique tenant identifiers.

## Membership API

Implemented membership endpoints:

- `GET /orgs/{org_id}/members`: requires tenant membership and `manage_members` permission, so only `owner` and `admin` members can list member records.
- `POST /orgs/{org_id}/members`: adds an existing user to the organisation, rejects duplicate memberships, prevents admins from granting `owner`, and writes a `member.added` audit event with secret-safe metadata.
- `PATCH /orgs/{org_id}/members/{user_id}`: changes a member role, prevents admins from changing owner memberships or granting `owner`, protects the final owner from downgrade, and writes a `member.role_changed` audit event.
- `DELETE /orgs/{org_id}/members/{user_id}`: removes a member, prevents admins from removing owners, protects the final owner from removal, and writes a `member.removed` audit event.

Membership responses embed only public user data (`id`, `email`, `display_name`, and `is_active`) and never include password hashes.

## Project API

Implemented project endpoints:

- `POST /orgs/{org_id}/projects`: creates a project inside one organisation after tenant membership and `write_projects` checks. `owner`, `admin`, and `member` roles may create projects; `viewer` is read-only.
- `GET /orgs/{org_id}/projects`: lists non-deleted projects scoped to the requested organisation and supports `limit`/`offset` pagination, optional `status` filtering, optional case-insensitive `name` search, `sort_by` (`created_at`, `name`, or `status`), and `sort_direction` (`asc` or `desc`).
- `GET /orgs/{org_id}/projects/{project_id}`: fetches a project with both organisation ID and project ID in the repository lookup, so IDs from other tenants are not accessible.
- `PATCH /orgs/{org_id}/projects/{project_id}`: updates supplied project fields after `write_projects` checks and supports clearing `description` with `null`.
- `DELETE /orgs/{org_id}/projects/{project_id}`: soft-deletes a project after `write_projects` checks, excluding it from default project reads/lists.

Project create, update, and delete workflows write `project.created`, `project.updated`, and `project.deleted` audit events with secret-safe metadata only. Project endpoints accept either a user bearer access token with the required project permission or an active API key scoped to the same organisation. Cross-tenant API key access is denied.

## API key API

Implemented API key endpoints:

- `POST /orgs/{org_id}/api-keys`: requires tenant membership and `manage_api_keys`, so only `owner` and `admin` members can create API keys. The response returns the raw key exactly once and persists only a deterministic key hash plus a short identification prefix.
- `GET /orgs/{org_id}/api-keys`: requires `manage_api_keys` and returns paginated metadata only; raw keys and key hashes are never included.
- `DELETE /orgs/{org_id}/api-keys/{api_key_id}`: requires `manage_api_keys`, revokes the key, and writes an `api_key.revoked` audit event with secret-safe metadata.

API keys authenticate with `Authorization: Bearer <raw_key>` on project endpoints only. They cannot manage members or create/list/revoke API keys. Revoked keys are excluded from authentication lookup.

## Audit API

Implemented audit endpoint:

- `GET /orgs/{org_id}/audit-events`: requires tenant membership and `read_audit_events`, so only `owner` and `admin` members can read audit logs. `member`, `viewer`, non-member, and cross-tenant requests are denied before audit rows are listed. Responses use `limit`/`offset` pagination metadata and return newest events first.

Audit event creation is centralised in an append-only audit service used by core business workflows. The service records registration/login, organisation create/update, member add/role-change/remove, project create/update/delete, and API key create/revoke events. It exposes no public update/delete workflow for audit events and rejects obvious secret-bearing metadata fields such as passwords, password hashes, raw API keys, key hashes, bearer tokens, and authorization values. API key metadata may include non-secret labels and short key prefixes for operator identification.

## Metrics

Implemented Prometheus metrics endpoint:

- `GET /metrics`: returns Prometheus text exposition from the app-local metrics registry without requiring authentication so a local scraper can collect it.
- HTTP request metrics use route templates rather than raw tenant or resource IDs to avoid high-cardinality labels.
- Business metrics cover auth attempts, organisations created, projects created, API keys created/revoked, audit events recorded, and idempotency replay/conflict outcomes.

Primary metric families:

- `saas_api_requests_total`
- `saas_api_request_duration_seconds`
- `saas_api_auth_attempts_total`
- `saas_api_organisations_created_total`
- `saas_api_projects_created_total`
- `saas_api_api_keys_created_total`
- `saas_api_api_keys_revoked_total`
- `saas_api_audit_events_recorded_total`
- `saas_api_idempotency_replays_total`
- `saas_api_idempotency_conflicts_total`

The local Compose stack starts Prometheus and Grafana containers with repository-owned configuration:

- Prometheus config: `observability/prometheus/prometheus.yml`
- Grafana datasource provisioning: `observability/grafana/provisioning/datasources/prometheus.yml`
- Grafana dashboard provisioning: `observability/grafana/provisioning/dashboards/dashboards.yml`
- Grafana dashboard JSON: `observability/grafana/dashboards/saas-api-overview.json`

Local observability URLs when `docker compose up --build` is running:

- API metrics: <http://localhost:8000/metrics>
- Prometheus UI: <http://localhost:9090>
- Prometheus target health: <http://localhost:9090/targets>
- Grafana UI: <http://localhost:3000> (`admin` / `local-placeholder-grafana-password`)
- Grafana dashboard: **Dashboards** → **Portfolio SaaS API** → **Multi-Tenant SaaS API Overview**

The committed Grafana login values are local placeholders only. Production systems need managed secrets, authenticated dashboards, alerting rules, retention/storage planning, and reviewed network exposure.

## Idempotency

Implemented creation idempotency:

- `POST /orgs`, `POST /orgs/{org_id}/projects`, and `POST /orgs/{org_id}/api-keys` accept an optional `Idempotency-Key` header.
- Records are scoped by authenticated principal, HTTP method, path, request body hash, and organisation ID where applicable so keys cannot replay behaviour across users, API keys, tenants, methods, or endpoints.
- Reusing the same key and body returns the stored response with `Idempotency-Replayed: true`.
- Reusing the same key with a different body returns `409 Conflict` without exposing the stored or incoming body hash.
- Organisation-scoped idempotent replays still perform current tenant permission checks before returning stored project or API key creation responses.
- API key creation snapshots intentionally omit one-time raw key material. The initial create response returns `raw_key`; replay responses return stored API key metadata plus an `idempotency_replay` note and never return or persist the raw key.
