from pytest import raises

from multi_tenant_saas_api.domain import (
    OrganisationRole,
    Permission,
    ProjectSortField,
    ProjectStatus,
    SortDirection,
    permissions_for_role,
    role_has_permission,
)


def test_role_validation_accepts_declared_roles() -> None:
    assert OrganisationRole("owner") is OrganisationRole.OWNER
    assert OrganisationRole("admin") is OrganisationRole.ADMIN
    assert OrganisationRole("member") is OrganisationRole.MEMBER
    assert OrganisationRole("viewer") is OrganisationRole.VIEWER


def test_role_validation_rejects_unknown_roles() -> None:
    with raises(ValueError):
        OrganisationRole("superuser")


def test_project_status_validation_accepts_declared_statuses() -> None:
    assert ProjectStatus("active") is ProjectStatus.ACTIVE
    assert ProjectStatus("archived") is ProjectStatus.ARCHIVED


def test_project_sort_validation_accepts_declared_fields_and_directions() -> None:
    assert ProjectSortField("created_at") is ProjectSortField.CREATED_AT
    assert ProjectSortField("name") is ProjectSortField.NAME
    assert ProjectSortField("status") is ProjectSortField.STATUS
    assert SortDirection("asc") is SortDirection.ASC
    assert SortDirection("desc") is SortDirection.DESC


def test_permission_mapping_grants_expected_owner_permissions() -> None:
    owner_permissions = permissions_for_role(OrganisationRole.OWNER)

    assert Permission.MANAGE_ORGANISATION in owner_permissions
    assert Permission.MANAGE_MEMBERS in owner_permissions
    assert Permission.MANAGE_API_KEYS in owner_permissions
    assert Permission.WRITE_PROJECTS in owner_permissions
    assert Permission.READ_AUDIT_EVENTS in owner_permissions


def test_permission_mapping_grants_expected_admin_permissions() -> None:
    assert role_has_permission(OrganisationRole.ADMIN, Permission.UPDATE_ORGANISATION)
    assert role_has_permission(OrganisationRole.ADMIN, Permission.MANAGE_MEMBERS)
    assert role_has_permission(OrganisationRole.ADMIN, Permission.MANAGE_API_KEYS)
    assert role_has_permission(OrganisationRole.ADMIN, Permission.WRITE_PROJECTS)
    assert role_has_permission(OrganisationRole.ADMIN, Permission.READ_AUDIT_EVENTS)
    assert not role_has_permission(OrganisationRole.ADMIN, Permission.MANAGE_ORGANISATION)


def test_permission_mapping_limits_member_and_viewer_permissions() -> None:
    assert role_has_permission(OrganisationRole.MEMBER, Permission.WRITE_PROJECTS)
    assert not role_has_permission(OrganisationRole.MEMBER, Permission.MANAGE_MEMBERS)
    assert not role_has_permission(OrganisationRole.MEMBER, Permission.READ_AUDIT_EVENTS)

    assert role_has_permission(OrganisationRole.VIEWER, Permission.READ_PROJECTS)
    assert not role_has_permission(OrganisationRole.VIEWER, Permission.WRITE_PROJECTS)
    assert not role_has_permission(OrganisationRole.VIEWER, Permission.MANAGE_API_KEYS)
