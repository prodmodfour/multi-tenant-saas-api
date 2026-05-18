# Documentation

Project documentation will be expanded as implementation tickets add architecture, API behaviour, operations, security guidance, runbooks, and ADRs.

## Role model

Organisations are the tenant boundary. Tenant-scoped business services must resolve the current authenticated principal, load the principal's organisation membership, and enforce role permissions before reading or mutating tenant-owned data.

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

Project create, update, and delete workflows write `project.created`, `project.updated`, and `project.deleted` audit events with secret-safe metadata only.
