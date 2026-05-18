"""RBAC and tenant-context services.

This module contains framework-agnostic services for resolving authenticated
principals, looking up organisation memberships, enforcing role permissions, and
protecting the invariant that every organisation keeps at least one owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.database import Organisation, OrganisationMembership, User
from multi_tenant_saas_api.domain import (
    MembershipID,
    OrganisationID,
    OrganisationRole,
    Permission,
    UserID,
    permissions_for_role,
)
from multi_tenant_saas_api.repositories import (
    MembershipRepository,
    OrganisationRepository,
    UserRepository,
)
from multi_tenant_saas_api.services.auth import AccessTokenError, AccessTokenService, PrincipalType


class RBACServiceError(ValueError):
    """Base class for safe RBAC and tenant-context workflow errors."""


class PrincipalResolutionError(RBACServiceError):
    """Raised when bearer credentials cannot resolve an active user principal."""


class OrganisationNotFoundError(RBACServiceError):
    """Raised when an organisation tenant does not exist."""


class TenantAccessDeniedError(RBACServiceError):
    """Raised when a principal is not a member of an organisation tenant."""


class PermissionDeniedError(TenantAccessDeniedError):
    """Raised when a tenant member lacks a required permission."""


class LastOwnerProtectionError(RBACServiceError):
    """Raised when an operation would leave an organisation with no owner."""


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    """Secret-safe authenticated user principal resolved from bearer auth."""

    principal_type: PrincipalType
    user_id: UserID
    email: str
    display_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Authorised principal plus organisation membership and permissions."""

    principal: CurrentPrincipal
    organisation_id: OrganisationID
    organisation_name: str
    organisation_slug: str
    membership_id: MembershipID
    role: OrganisationRole
    permissions: frozenset[Permission]

    def has_permission(self, permission: Permission) -> bool:
        """Return whether this context grants ``permission``."""

        return permission in self.permissions

    def require_permission(self, permission: Permission) -> None:
        """Raise a safe error if this context lacks ``permission``."""

        if not self.has_permission(permission):
            raise PermissionDeniedError("insufficient permissions for this organisation")


class PrincipalResolverService:
    """Resolve bearer access tokens into active user principals."""

    __slots__ = ("_tokens", "_users")

    def __init__(
        self,
        *,
        token_service: AccessTokenService,
        user_repository: UserRepository,
    ) -> None:
        """Initialise principal resolution dependencies."""

        self._tokens = token_service
        self._users = user_repository

    async def resolve_user_principal(self, *, bearer_token: str) -> CurrentPrincipal:
        """Validate a bearer token and return an active user principal.

        All failure modes intentionally collapse to one safe exception so API
        routes can avoid revealing whether a token was malformed, expired, or
        pointed at a missing/inactive user.
        """

        try:
            token_principal = self._tokens.validate_access_token(bearer_token)
        except AccessTokenError as exc:
            raise PrincipalResolutionError("invalid or expired access token") from exc

        if token_principal.principal_type is not PrincipalType.USER:
            raise PrincipalResolutionError("invalid or expired access token")

        user = await self._users.get_by_id(_uuid_from_user_id(token_principal.user_id))
        if user is None or not user.is_active:
            raise PrincipalResolutionError("invalid or expired access token")

        return _current_principal_from_model(user)


class RBACService:
    """Resolve tenant contexts and enforce organisation-level permissions."""

    __slots__ = ("_memberships", "_organisations", "_principals")

    def __init__(
        self,
        *,
        session: AsyncSession,
        token_service: AccessTokenService,
        user_repository: UserRepository | None = None,
        membership_repository: MembershipRepository | None = None,
        organisation_repository: OrganisationRepository | None = None,
        principal_resolver: PrincipalResolverService | None = None,
    ) -> None:
        """Initialise RBAC dependencies with repository-layer collaborators."""

        users = user_repository or UserRepository(session)
        self._memberships = membership_repository or MembershipRepository(session)
        self._organisations = organisation_repository or OrganisationRepository(session)
        self._principals = principal_resolver or PrincipalResolverService(
            token_service=token_service,
            user_repository=users,
        )

    async def resolve_current_principal(self, *, bearer_token: str) -> CurrentPrincipal:
        """Resolve the current active user principal from a bearer token."""

        return await self._principals.resolve_user_principal(bearer_token=bearer_token)

    async def get_tenant_context(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        required_permission: Permission | None = None,
    ) -> TenantContext:
        """Return tenant context after organisation, membership, and RBAC checks.

        Unknown organisations raise ``OrganisationNotFoundError``. Existing
        organisations where the principal is not a member raise
        ``TenantAccessDeniedError``. Existing memberships without the required
        permission raise ``PermissionDeniedError``.
        """

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        organisation = await self._organisations.get_by_id(organisation_uuid)
        if organisation is None:
            raise OrganisationNotFoundError("organisation was not found")

        membership = await self._memberships.get_for_user(
            organisation_id=organisation_uuid,
            user_id=_uuid_from_user_id(principal.user_id),
        )
        if membership is None:
            raise TenantAccessDeniedError("principal is not a member of this organisation")

        context = _tenant_context_from_models(
            principal=principal,
            organisation=organisation,
            membership=membership,
        )
        if required_permission is not None:
            context.require_permission(required_permission)
        return context

    @staticmethod
    def require_permission(context: TenantContext, permission: Permission) -> None:
        """Raise a safe error when ``context`` does not grant ``permission``."""

        context.require_permission(permission)

    async def protect_last_owner(
        self,
        *,
        organisation_id: UUID | OrganisationID,
        target_user_id: UUID | UserID,
        new_role: OrganisationRole | None,
    ) -> None:
        """Prevent removing or downgrading the final owner in an organisation.

        Pass ``new_role=None`` for membership removal. Passing
        ``new_role=OrganisationRole.OWNER`` is always safe because the target
        remains an owner.
        """

        if new_role is OrganisationRole.OWNER:
            return

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        target_user_uuid = _uuid_from_user_id(target_user_id)
        if await self._memberships.is_last_owner(
            organisation_id=organisation_uuid,
            user_id=target_user_uuid,
        ):
            raise LastOwnerProtectionError("organisation must always have at least one owner")


def _current_principal_from_model(user: User) -> CurrentPrincipal:
    """Build secret-safe principal data from a user model."""

    return CurrentPrincipal(
        principal_type=PrincipalType.USER,
        user_id=UserID(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _tenant_context_from_models(
    *,
    principal: CurrentPrincipal,
    organisation: Organisation,
    membership: OrganisationMembership,
) -> TenantContext:
    """Build a tenant context from repository-returned models."""

    return TenantContext(
        principal=principal,
        organisation_id=OrganisationID(organisation.id),
        organisation_name=organisation.name,
        organisation_slug=organisation.slug,
        membership_id=MembershipID(membership.id),
        role=membership.role,
        permissions=permissions_for_role(membership.role),
    )


def _uuid_from_user_id(user_id: UUID | UserID) -> UUID:
    """Return the runtime UUID value held by a user identifier."""

    return UUID(str(user_id))


def _uuid_from_organisation_id(organisation_id: UUID | OrganisationID) -> UUID:
    """Return the runtime UUID value held by an organisation identifier."""

    return UUID(str(organisation_id))


__all__ = [
    "CurrentPrincipal",
    "LastOwnerProtectionError",
    "OrganisationNotFoundError",
    "PermissionDeniedError",
    "PrincipalResolutionError",
    "PrincipalResolverService",
    "RBACService",
    "RBACServiceError",
    "TenantAccessDeniedError",
    "TenantContext",
]
