# API walkthrough

This walkthrough describes the implemented API surface and the expected order of
operations for a local demo. It uses placeholders only; do not paste real bearer
tokens, raw API keys, passwords, or private IDs into committed files.

For interactive exploration, start the local stack and open the docs that Compose
enables for local use:

```bash
docker compose up --build
```

- API: <http://localhost:8000>
- OpenAPI UI: <http://localhost:8000/docs>
- Health: <http://localhost:8000/healthz>
- Readiness: <http://localhost:8000/readyz>
- Metrics: <http://localhost:8000/metrics>

OpenAPI is disabled by default outside explicitly configured local exploration.

## 1. Register a user

`POST /auth/register` creates a local demo user and stores only a password hash.

```http
POST /auth/register
Content-Type: application/json
```

```json
{
  "email": "owner@example.com",
  "password": "<demo-password-at-least-12-characters>",
  "display_name": "Owner User"
}
```

Success returns `201 Created` with public user fields only:

```json
{
  "user": {
    "id": "<user-id>",
    "email": "owner@example.com",
    "display_name": "Owner User",
    "is_active": true,
    "created_at": "<timestamp>",
    "updated_at": "<timestamp>"
  }
}
```

Duplicate email registration returns `409 Conflict`. Invalid email or password
policy failures return validation errors.

## 2. Login and call current-user endpoint

`POST /auth/login` validates credentials and returns a short-lived bearer token.

```http
POST /auth/login
Content-Type: application/json
```

```json
{
  "email": "owner@example.com",
  "password": "<demo-password-at-least-12-characters>"
}
```

```json
{
  "access_token": "<access-token>",
  "token_type": "bearer",
  "expires_in_seconds": 900
}
```

Use the token on protected user routes:

```http
GET /me
Authorization: Bearer <access-token>
```

The response includes public user fields and organisation memberships. A new user
has an empty memberships list until an organisation is created or the user is
added to one.

## 3. Create an organisation tenant

`POST /orgs` creates a tenant and automatically makes the creator an `owner`.
The slug is generated from the name when omitted.

```http
POST /orgs
Authorization: Bearer <access-token>
Idempotency-Key: <stable-operation-key>
Content-Type: application/json
```

```json
{
  "name": "Acme Demo",
  "slug": "acme-demo"
}
```

The response contains organisation metadata. Reusing the same idempotency key with
the same body returns the stored response and `Idempotency-Replayed: true`.
Reusing the key with a different body returns `409 Conflict`.

Organisation endpoints:

| Method and path | Access |
| --- | --- |
| `POST /orgs` | Authenticated user. |
| `GET /orgs` | Authenticated user; returns only organisations where the user is a member. |
| `GET /orgs/{organisation_id}` | Tenant member with `read_organisation`. |
| `PATCH /orgs/{organisation_id}` | Tenant `owner` or `admin`. |

Organisation slugs are globally unique; names are not.

## 4. Add and manage members

Create or identify a second user, then add that existing user to the organisation.
Only `owner` and `admin` users can manage memberships. Admin users cannot grant,
change, or remove owner memberships.

```http
POST /orgs/{organisation_id}/members
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "user_id": "<second-user-id>",
  "role": "member"
}
```

Membership endpoints:

| Method and path | Behaviour |
| --- | --- |
| `GET /orgs/{organisation_id}/members` | Owner/admin list with pagination. |
| `POST /orgs/{organisation_id}/members` | Add an existing user. |
| `PATCH /orgs/{organisation_id}/members/{user_id}` | Change the user's role. |
| `DELETE /orgs/{organisation_id}/members/{user_id}` | Remove the user's membership. |

The last owner cannot be downgraded or removed; those attempts return
`409 Conflict`.

## 5. Work with projects

Projects belong to exactly one organisation. User access requires membership and
project permissions. Active API keys for the same organisation can also use
project endpoints.

```http
POST /orgs/{organisation_id}/projects
Authorization: Bearer <access-token>
Idempotency-Key: <stable-operation-key>
Content-Type: application/json
```

```json
{
  "name": "Launch Checklist",
  "description": "Public-safe demo project",
  "status": "active"
}
```

Project endpoints:

| Method and path | Access |
| --- | --- |
| `POST /orgs/{organisation_id}/projects` | Owner/admin/member or active same-organisation API key. |
| `GET /orgs/{organisation_id}/projects` | Owner/admin/member/viewer or active same-organisation API key. |
| `GET /orgs/{organisation_id}/projects/{project_id}` | Same as list. |
| `PATCH /orgs/{organisation_id}/projects/{project_id}` | Owner/admin/member or active same-organisation API key. |
| `DELETE /orgs/{organisation_id}/projects/{project_id}` | Owner/admin/member or active same-organisation API key. |

List query parameters:

| Parameter | Description |
| --- | --- |
| `limit` | Page size from 1 to 100; default `50`. |
| `offset` | Zero-based offset; default `0`. |
| `status` | Optional `active` or `archived` filter. |
| `name` | Optional case-insensitive name search. |
| `sort_by` | `created_at`, `name`, or `status`; default `created_at`. |
| `sort_direction` | `asc` or `desc`; default `desc`. |

Example list path:

```text
/orgs/{organisation_id}/projects?limit=20&offset=0&status=active&name=Launch&sort_by=name&sort_direction=asc
```

Delete is a soft delete; default project reads and lists exclude deleted rows.

## 6. Create and use an API key

Owner/admin users can create organisation API keys. Raw key material appears only
in the initial create response.

```http
POST /orgs/{organisation_id}/api-keys
Authorization: Bearer <access-token>
Idempotency-Key: <stable-operation-key>
Content-Type: application/json
```

```json
{
  "name": "Local demo automation"
}
```

Initial response shape:

```json
{
  "api_key": {
    "id": "<api-key-id>",
    "organisation_id": "<organisation-id>",
    "name": "Local demo automation",
    "key_prefix": "<key-prefix>",
    "created_by_user_id": "<user-id>",
    "revoked_at": null,
    "last_used_at": null,
    "created_at": "<timestamp>",
    "updated_at": "<timestamp>"
  },
  "raw_key": "<api-key-shown-once>"
}
```

An idempotent replay of API key creation returns metadata plus a replay note and
does not return `raw_key`.

Use the raw key only on project endpoints:

```http
GET /orgs/{organisation_id}/projects
Authorization: Bearer <api-key-shown-once>
```

API key management endpoints require user bearer tokens and owner/admin
permissions:

| Method and path | Behaviour |
| --- | --- |
| `POST /orgs/{organisation_id}/api-keys` | Create a key and show raw key once. |
| `GET /orgs/{organisation_id}/api-keys` | List metadata only. |
| `DELETE /orgs/{organisation_id}/api-keys/{api_key_id}` | Revoke a key. |

Revoked keys cannot authenticate. API keys cannot access other tenants and cannot
manage members, API keys, or audit logs.

## 7. Read audit events

Owner/admin users can read audit events for their organisation:

```http
GET /orgs/{organisation_id}/audit-events?limit=50&offset=0
Authorization: Bearer <access-token>
```

Audit responses are newest-first and paginated. Metadata is secret-safe and does
not contain passwords, password hashes, bearer tokens, raw API keys, or key
hashes.

## 8. Check health, readiness, and metrics

System endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Lightweight liveness; does not check dependencies. |
| `GET /readyz` | PostgreSQL readiness; returns `503` when unavailable. |
| `GET /metrics` | Prometheus text metrics for local scraping. |

`/metrics` includes HTTP request counters and duration histograms plus business
workflow counters for auth attempts, created organisations/projects/API keys,
revoked API keys, audit events, and idempotency replay/conflict outcomes.

## Common response patterns

- `401 Unauthorized`: missing, invalid, or expired bearer token/API key.
- `403 Forbidden`: authenticated principal lacks tenant access or permission.
- `404 Not Found`: requested organisation or tenant-scoped resource is not
  available in the requested scope.
- `409 Conflict`: duplicate slug/membership, last-owner protection, or
  idempotency body mismatch.
- `422 Unprocessable Entity`: request schema or field validation failure.

List responses use a consistent shape:

```json
{
  "items": [],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 0,
    "count": 0
  }
}
```
