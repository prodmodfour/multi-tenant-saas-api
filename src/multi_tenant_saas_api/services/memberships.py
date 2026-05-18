"""Organisation membership management workflows.

This module owns member listing, creation, role changes, and removal. It keeps
HTTP routes thin while enforcing tenant membership, RBAC, last-owner protection,
transaction handling, and secret-safe audit event creation in the service layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.database import OrganisationMembership, User
from multi_tenant_saas_api.domain import (
    AuditAction,
    MembershipID,
    OrganisationID,
    OrganisationRole,
    Permission,
    UserID,
)
from multi_tenant_saas_api.observability import MetricsRecorder, NoOpMetricsRecorder
from multi_tenant_saas_api.repositories import MembershipRepository, UserRepository
from multi_tenant_saas_api.services.audit import AuditService
from multi_tenant_saas_api.services.rbac import (
    CurrentPrincipal,
    PermissionDeniedError,
    RBACService,
    TenantContext,
)


class MembershipAPIServiceError(ValueError):
    """Base class for safe membership API workflow errors."""


class MembershipAlreadyExistsError(MembershipAPIServiceError):
    """Raised when a user already belongs to an organisation."""


class MembershipNotFoundError(MembershipAPIServiceError):
    """Raised when a requested organisation membership does not exist."""


class TargetUserNotFoundError(MembershipAPIServiceError):
    """Raised when a member-management request references an unknown user."""


@dataclass(frozen=True, slots=True)
class PublicMembershipUser:
    """User data safe to embed in organisation membership responses."""

    id: UserID
    email: str
    display_name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class PublicMembership:
    """Organisation membership data safe to return from API workflows."""

    id: MembershipID
    organisation_id: OrganisationID
    user: PublicMembershipUser
    role: OrganisationRole
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MembershipList:
    """Paginated organisation membership list."""

    items: list[PublicMembership]
    limit: int
    offset: int
    total: int


class MembershipAPIService:
    """Service layer for organisation membership management endpoints."""

    __slots__ = ("_audit", "_memberships", "_metrics", "_rbac", "_session", "_users")

    def __init__(
        self,
        *,
        session: AsyncSession,
        rbac_service: RBACService,
        user_repository: UserRepository | None = None,
        membership_repository: MembershipRepository | None = None,
        audit_service: AuditService | None = None,
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        """Initialise membership workflows with repository collaborators."""

        self._session = session
        self._rbac = rbac_service
        self._users = user_repository or UserRepository(session)
        self._memberships = membership_repository or MembershipRepository(session)
        self._metrics = metrics_recorder or NoOpMetricsRecorder()
        self._audit = audit_service or AuditService(
            session=session,
            metrics_recorder=self._metrics,
        )

    async def list_members(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        limit: int,
        offset: int,
    ) -> MembershipList:
        """List organisation members after tenant and manage-members checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.MANAGE_MEMBERS,
        )

        memberships = await self._memberships.list_for_organisation(
            organisation_id=organisation_uuid,
            limit=limit,
            offset=offset,
        )
        items = [await self._public_membership_from_model(membership) for membership in memberships]
        total = await self._memberships.count_for_organisation(organisation_uuid)
        return MembershipList(items=items, limit=limit, offset=offset, total=total)

    async def add_member(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        target_user_id: UUID | UserID,
        role: OrganisationRole,
    ) -> PublicMembership:
        """Add an existing user to an organisation."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        target_user_uuid = _uuid_from_user_id(target_user_id)
        context = await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.MANAGE_MEMBERS,
        )
        _ensure_role_management_allowed(context, target_role=None, requested_role=role)

        target_user = await self._users.get_by_id(target_user_uuid)
        if target_user is None:
            raise TargetUserNotFoundError("user was not found")

        existing_membership = await self._memberships.get_for_user(
            organisation_id=organisation_uuid,
            user_id=target_user_uuid,
        )
        if existing_membership is not None:
            raise MembershipAlreadyExistsError("user is already a member of this organisation")

        try:
            membership = await self._memberships.create(
                organisation_id=organisation_uuid,
                user_id=target_user_uuid,
                role=role,
            )
            await self._audit.record_event(
                action=AuditAction.MEMBER_ADDED,
                organisation_id=organisation_uuid,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="membership",
                target_id=membership.id,
                metadata={"user_id": str(target_user_uuid), "role": role.value},
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise MembershipAlreadyExistsError(
                "user is already a member of this organisation"
            ) from exc
        except Exception:
            await self._session.rollback()
            raise

        return _public_membership_from_models(membership=membership, user=target_user)

    async def update_member_role(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        target_user_id: UUID | UserID,
        role: OrganisationRole,
    ) -> PublicMembership:
        """Change an organisation member's role with last-owner protection."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        target_user_uuid = _uuid_from_user_id(target_user_id)
        context = await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.MANAGE_MEMBERS,
        )
        membership = await self._memberships.get_for_user(
            organisation_id=organisation_uuid,
            user_id=target_user_uuid,
        )
        if membership is None:
            raise MembershipNotFoundError("membership was not found")

        old_role = membership.role
        _ensure_role_management_allowed(context, target_role=old_role, requested_role=role)
        await self._protect_if_owner_would_be_removed(
            organisation_id=organisation_uuid,
            target_user_id=target_user_uuid,
            current_role=old_role,
            new_role=role,
        )

        target_user = await self._users.get_by_id(target_user_uuid)
        if target_user is None:
            raise TargetUserNotFoundError("user was not found")

        try:
            updated_membership = await self._memberships.update_role(membership, role=role)
            await self._audit.record_event(
                action=AuditAction.MEMBER_ROLE_CHANGED,
                organisation_id=organisation_uuid,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="membership",
                target_id=updated_membership.id,
                metadata={
                    "user_id": str(target_user_uuid),
                    "old_role": old_role.value,
                    "new_role": role.value,
                },
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return _public_membership_from_models(membership=updated_membership, user=target_user)

    async def remove_member(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        target_user_id: UUID | UserID,
    ) -> None:
        """Remove a user from an organisation with last-owner protection."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        target_user_uuid = _uuid_from_user_id(target_user_id)
        context = await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.MANAGE_MEMBERS,
        )
        membership = await self._memberships.get_for_user(
            organisation_id=organisation_uuid,
            user_id=target_user_uuid,
        )
        if membership is None:
            raise MembershipNotFoundError("membership was not found")

        _ensure_role_management_allowed(context, target_role=membership.role, requested_role=None)
        await self._protect_if_owner_would_be_removed(
            organisation_id=organisation_uuid,
            target_user_id=target_user_uuid,
            current_role=membership.role,
            new_role=None,
        )

        removed_role = membership.role
        membership_id = membership.id
        try:
            await self._memberships.delete(membership)
            await self._audit.record_event(
                action=AuditAction.MEMBER_REMOVED,
                organisation_id=organisation_uuid,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="membership",
                target_id=membership_id,
                metadata={"user_id": str(target_user_uuid), "role": removed_role.value},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def _public_membership_from_model(
        self,
        membership: OrganisationMembership,
    ) -> PublicMembership:
        """Return a public membership DTO from a repository membership model."""

        user = await self._users.get_by_id(membership.user_id)
        if user is None:
            raise TargetUserNotFoundError("user was not found")
        return _public_membership_from_models(membership=membership, user=user)

    async def _protect_if_owner_would_be_removed(
        self,
        *,
        organisation_id: UUID,
        target_user_id: UUID,
        current_role: OrganisationRole,
        new_role: OrganisationRole | None,
    ) -> None:
        """Invoke the RBAC last-owner helper only for owner removal/downgrade paths."""

        if current_role is not OrganisationRole.OWNER:
            return
        if new_role is OrganisationRole.OWNER:
            return
        await self._rbac.protect_last_owner(
            organisation_id=organisation_id,
            target_user_id=target_user_id,
            new_role=new_role,
        )


def _ensure_role_management_allowed(
    context: TenantContext,
    *,
    target_role: OrganisationRole | None,
    requested_role: OrganisationRole | None,
) -> None:
    """Enforce owner/admin member-management boundaries."""

    if context.role is OrganisationRole.OWNER:
        return
    if context.role is OrganisationRole.ADMIN:
        if target_role is OrganisationRole.OWNER or requested_role is OrganisationRole.OWNER:
            raise PermissionDeniedError("insufficient permissions for this organisation")
        return
    raise PermissionDeniedError("insufficient permissions for this organisation")


def _public_membership_from_models(
    *,
    membership: OrganisationMembership,
    user: User,
) -> PublicMembership:
    """Convert repository models to a secret-safe membership DTO."""

    return PublicMembership(
        id=MembershipID(membership.id),
        organisation_id=OrganisationID(membership.organisation_id),
        user=PublicMembershipUser(
            id=UserID(user.id),
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
        ),
        role=membership.role,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _uuid_from_user_id(user_id: UUID | UserID) -> UUID:
    """Return the runtime UUID value held by a typed user identifier."""

    return UUID(str(user_id))


def _uuid_from_organisation_id(organisation_id: UUID | OrganisationID) -> UUID:
    """Return the runtime UUID value held by a typed organisation identifier."""

    return UUID(str(organisation_id))


__all__ = [
    "MembershipAPIService",
    "MembershipAPIServiceError",
    "MembershipAlreadyExistsError",
    "MembershipList",
    "MembershipNotFoundError",
    "PublicMembership",
    "PublicMembershipUser",
    "TargetUserNotFoundError",
]
