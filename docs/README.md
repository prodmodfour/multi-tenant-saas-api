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
