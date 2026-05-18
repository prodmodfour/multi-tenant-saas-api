# Documentation

Project documentation will be expanded as implementation tickets add architecture, API behaviour, operations, security guidance, runbooks, and ADRs.

## Role model

Organisations are the tenant boundary. Tenant-scoped business services must resolve the current authenticated principal, load the principal's organisation membership, and enforce role permissions before reading or mutating tenant-owned data.

Roles:

- `owner`: manage organisation, manage members, manage API keys, read/write projects, read audit events.
- `admin`: update organisation metadata, manage members, manage API keys, read/write projects, read audit events.
- `member`: read organisation metadata and read/write projects.
- `viewer`: read organisation metadata and read projects only.

Every organisation must retain at least one owner. The RBAC service includes last-owner protection so future member-management workflows cannot remove or downgrade the final owner.

## Organisation API

Implemented organisation endpoints:

- `POST /orgs`: creates an organisation for the current bearer-token user, derives a slug from the name when omitted, enforces unique slugs, makes the creator an `owner`, and writes an `organisation.created` audit event with secret-safe metadata.
- `GET /orgs`: lists only organisations where the current user has a membership and returns `limit`/`offset` pagination metadata.
- `GET /orgs/{org_id}`: requires tenant membership and `read_organisation` permission.
- `PATCH /orgs/{org_id}`: requires tenant membership and `update_organisation` permission, so `owner` and `admin` can update metadata while `member` and `viewer` are denied.

Organisation names are not globally unique; slugs are the unique tenant identifiers.
