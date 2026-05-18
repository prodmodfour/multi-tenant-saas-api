"""Domain identifiers, roles, permissions, and lifecycle enums."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import NewType
from uuid import UUID

UserID = NewType("UserID", UUID)
OrganisationID = NewType("OrganisationID", UUID)
MembershipID = NewType("MembershipID", UUID)
ProjectID = NewType("ProjectID", UUID)
APIKeyID = NewType("APIKeyID", UUID)
AuditEventID = NewType("AuditEventID", UUID)


class OrganisationRole(StrEnum):
    """Roles a user can hold within an organisation tenant."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Permission(StrEnum):
    """Fine-grained permissions used by service-level RBAC checks."""

    READ_ORGANISATION = "read_organisation"
    UPDATE_ORGANISATION = "update_organisation"
    MANAGE_ORGANISATION = "manage_organisation"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_API_KEYS = "manage_api_keys"
    READ_PROJECTS = "read_projects"
    WRITE_PROJECTS = "write_projects"
    READ_AUDIT_EVENTS = "read_audit_events"


class ProjectStatus(StrEnum):
    """Supported lifecycle states for organisation-scoped projects."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class AuditAction(StrEnum):
    """Business actions recorded in append-only audit events."""

    USER_REGISTERED = "user.registered"
    USER_LOGGED_IN = "user.logged_in"
    ORGANISATION_CREATED = "organisation.created"
    ORGANISATION_UPDATED = "organisation.updated"
    MEMBER_ADDED = "member.added"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_REMOVED = "member.removed"
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"


_ROLE_PERMISSIONS: dict[OrganisationRole, frozenset[Permission]] = {
    OrganisationRole.OWNER: frozenset(Permission),
    OrganisationRole.ADMIN: frozenset(
        {
            Permission.READ_ORGANISATION,
            Permission.UPDATE_ORGANISATION,
            Permission.MANAGE_MEMBERS,
            Permission.MANAGE_API_KEYS,
            Permission.READ_PROJECTS,
            Permission.WRITE_PROJECTS,
            Permission.READ_AUDIT_EVENTS,
        }
    ),
    OrganisationRole.MEMBER: frozenset(
        {
            Permission.READ_ORGANISATION,
            Permission.READ_PROJECTS,
            Permission.WRITE_PROJECTS,
        }
    ),
    OrganisationRole.VIEWER: frozenset(
        {
            Permission.READ_ORGANISATION,
            Permission.READ_PROJECTS,
        }
    ),
}

ROLE_PERMISSIONS: Mapping[OrganisationRole, frozenset[Permission]] = MappingProxyType(
    _ROLE_PERMISSIONS
)


def permissions_for_role(role: OrganisationRole) -> frozenset[Permission]:
    """Return the immutable permission set granted to an organisation role."""

    return ROLE_PERMISSIONS[role]


def role_has_permission(role: OrganisationRole, permission: Permission) -> bool:
    """Return whether ``role`` grants ``permission``."""

    return permission in permissions_for_role(role)


__all__ = [
    "APIKeyID",
    "AuditAction",
    "AuditEventID",
    "MembershipID",
    "OrganisationID",
    "OrganisationRole",
    "Permission",
    "ProjectID",
    "ProjectStatus",
    "ROLE_PERMISSIONS",
    "UserID",
    "permissions_for_role",
    "role_has_permission",
]
