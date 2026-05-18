from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pytest import raises
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ClauseElement

from multi_tenant_saas_api.database import Organisation, OrganisationMembership, User
from multi_tenant_saas_api.domain import OrganisationID, OrganisationRole, Permission, UserID
from multi_tenant_saas_api.services import AccessTokenService, PrincipalType
from multi_tenant_saas_api.services.rbac import (
    CurrentPrincipal,
    LastOwnerProtectionError,
    OrganisationNotFoundError,
    PermissionDeniedError,
    PrincipalResolutionError,
    RBACService,
    TenantAccessDeniedError,
)

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-rbac"
JWT_ISSUER = "multi-tenant-saas-api-rbac-test"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.scalar_results: list[object | None] = []
        self.scalar_statements: list[ClauseElement] = []

    async def scalar(self, statement: ClauseElement) -> object | None:
        self.scalar_statements.append(statement)
        if not self.scalar_results:
            return None
        return self.scalar_results.pop(0)


def as_session(fake: FakeSession) -> AsyncSession:
    return cast(AsyncSession, fake)


def token_service() -> AccessTokenService:
    return AccessTokenService(
        secret=JWT_SECRET,
        issuer=JWT_ISSUER,
        ttl_seconds=900,
    )


def make_service(fake: FakeSession) -> RBACService:
    return RBACService(
        session=as_session(fake),
        token_service=token_service(),
    )


def make_user(*, user_id: UUID | None = None, is_active: bool = True) -> User:
    return User(
        id=user_id or uuid4(),
        email="member@example.com",
        display_name="Member Example",
        password_hash="hashed-password-placeholder",
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def make_principal(*, user_id: UUID | None = None) -> CurrentPrincipal:
    return CurrentPrincipal(
        principal_type=PrincipalType.USER,
        user_id=UserID(user_id or uuid4()),
        email="member@example.com",
        display_name="Member Example",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def make_organisation(*, organisation_id: UUID | None = None) -> Organisation:
    return Organisation(
        id=organisation_id or uuid4(),
        name="Acme Demo",
        slug="acme-demo",
        created_at=NOW,
        updated_at=NOW,
    )


def make_membership(
    *,
    organisation_id: UUID,
    user_id: UUID,
    role: OrganisationRole,
) -> OrganisationMembership:
    return OrganisationMembership(
        id=uuid4(),
        organisation_id=organisation_id,
        user_id=user_id,
        role=role,
        created_at=NOW,
        updated_at=NOW,
    )


def test_resolves_current_principal_from_bearer_token_without_secret_fields() -> None:
    async def scenario() -> None:
        user_id = uuid4()
        user = make_user(user_id=user_id)
        fake = FakeSession()
        fake.scalar_results.append(user)
        service = make_service(fake)
        access_token = token_service().create_access_token(UserID(user_id))

        principal = await service.resolve_current_principal(bearer_token=access_token.token)

        assert principal.principal_type is PrincipalType.USER
        assert principal.user_id == UserID(user_id)
        assert principal.email == "member@example.com"
        assert principal.display_name == "Member Example"
        assert not hasattr(principal, "password_hash")
        assert len(fake.scalar_statements) == 1

    asyncio.run(scenario())


def test_current_principal_resolution_uses_safe_errors_for_invalid_or_inactive_users() -> None:
    async def scenario() -> None:
        invalid_token_fake = FakeSession()
        invalid_token_service = make_service(invalid_token_fake)
        with raises(PrincipalResolutionError, match="invalid or expired"):
            await invalid_token_service.resolve_current_principal(bearer_token="not-a-token")
        assert invalid_token_fake.scalar_statements == []

        inactive_user_id = uuid4()
        inactive_user_fake = FakeSession()
        inactive_user_fake.scalar_results.append(
            make_user(user_id=inactive_user_id, is_active=False)
        )
        inactive_user_service = make_service(inactive_user_fake)
        inactive_access_token = token_service().create_access_token(UserID(inactive_user_id))
        with raises(PrincipalResolutionError, match="invalid or expired"):
            await inactive_user_service.resolve_current_principal(
                bearer_token=inactive_access_token.token,
            )

    asyncio.run(scenario())


def test_tenant_context_enforces_owner_admin_member_and_viewer_permissions() -> None:
    async def scenario() -> None:
        cases: tuple[tuple[OrganisationRole, Permission, Permission | None], ...] = (
            (OrganisationRole.OWNER, Permission.MANAGE_ORGANISATION, None),
            (OrganisationRole.ADMIN, Permission.MANAGE_MEMBERS, Permission.MANAGE_ORGANISATION),
            (OrganisationRole.MEMBER, Permission.WRITE_PROJECTS, Permission.MANAGE_MEMBERS),
            (OrganisationRole.VIEWER, Permission.READ_PROJECTS, Permission.WRITE_PROJECTS),
        )

        for role, allowed_permission, denied_permission in cases:
            user_id = uuid4()
            organisation_id = uuid4()
            principal = make_principal(user_id=user_id)
            organisation = make_organisation(organisation_id=organisation_id)
            membership = make_membership(
                organisation_id=organisation_id,
                user_id=user_id,
                role=role,
            )
            fake = FakeSession()
            fake.scalar_results.extend([organisation, membership])
            service = make_service(fake)

            context = await service.get_tenant_context(
                principal=principal,
                organisation_id=OrganisationID(organisation_id),
                required_permission=allowed_permission,
            )

            assert context.principal is principal
            assert context.organisation_id == OrganisationID(organisation_id)
            assert context.organisation_name == "Acme Demo"
            assert context.role is role
            assert context.has_permission(allowed_permission)
            if role is OrganisationRole.OWNER:
                assert context.permissions == frozenset(Permission)
            if denied_permission is not None:
                assert not context.has_permission(denied_permission)
                with raises(PermissionDeniedError, match="insufficient permissions"):
                    service.require_permission(context, denied_permission)

    asyncio.run(scenario())


def test_tenant_context_reports_unknown_organisation_before_membership_lookup() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        fake.scalar_results.append(None)
        service = make_service(fake)

        with raises(OrganisationNotFoundError, match="organisation was not found"):
            await service.get_tenant_context(
                principal=make_principal(),
                organisation_id=uuid4(),
                required_permission=Permission.READ_ORGANISATION,
            )

        assert len(fake.scalar_statements) == 1

    asyncio.run(scenario())


def test_tenant_context_rejects_non_member_access() -> None:
    async def scenario() -> None:
        organisation_id = uuid4()
        fake = FakeSession()
        fake.scalar_results.extend([make_organisation(organisation_id=organisation_id), None])
        service = make_service(fake)

        with raises(TenantAccessDeniedError, match="not a member"):
            await service.get_tenant_context(
                principal=make_principal(),
                organisation_id=organisation_id,
                required_permission=Permission.READ_ORGANISATION,
            )

        assert len(fake.scalar_statements) == 2

    asyncio.run(scenario())


def test_last_owner_protection_blocks_removal_or_downgrade_of_final_owner() -> None:
    async def scenario() -> None:
        organisation_id = uuid4()
        owner_user_id = uuid4()
        owner_membership = make_membership(
            organisation_id=organisation_id,
            user_id=owner_user_id,
            role=OrganisationRole.OWNER,
        )

        downgrade_fake = FakeSession()
        downgrade_fake.scalar_results.extend([owner_membership, 0])
        downgrade_service = make_service(downgrade_fake)
        with raises(LastOwnerProtectionError, match="at least one owner"):
            await downgrade_service.protect_last_owner(
                organisation_id=organisation_id,
                target_user_id=owner_user_id,
                new_role=OrganisationRole.VIEWER,
            )

        removal_fake = FakeSession()
        removal_fake.scalar_results.extend([owner_membership, 0])
        removal_service = make_service(removal_fake)
        with raises(LastOwnerProtectionError, match="at least one owner"):
            await removal_service.protect_last_owner(
                organisation_id=organisation_id,
                target_user_id=owner_user_id,
                new_role=None,
            )

    asyncio.run(scenario())


def test_last_owner_protection_allows_safe_owner_changes() -> None:
    async def scenario() -> None:
        organisation_id = uuid4()
        owner_user_id = uuid4()
        owner_membership = make_membership(
            organisation_id=organisation_id,
            user_id=owner_user_id,
            role=OrganisationRole.OWNER,
        )

        still_owner_fake = FakeSession()
        still_owner_service = make_service(still_owner_fake)
        await still_owner_service.protect_last_owner(
            organisation_id=organisation_id,
            target_user_id=owner_user_id,
            new_role=OrganisationRole.OWNER,
        )
        assert still_owner_fake.scalar_statements == []

        other_owner_fake = FakeSession()
        other_owner_fake.scalar_results.extend([owner_membership, 1])
        other_owner_service = make_service(other_owner_fake)
        await other_owner_service.protect_last_owner(
            organisation_id=organisation_id,
            target_user_id=owner_user_id,
            new_role=OrganisationRole.ADMIN,
        )
        assert len(other_owner_fake.scalar_statements) == 2

    asyncio.run(scenario())
