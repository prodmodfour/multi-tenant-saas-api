"""Organisation tenant API workflows.

This module owns organisation creation, listing, detail, and update business
logic. It keeps HTTP routes thin while ensuring tenant membership checks,
permission checks, persistence, transaction handling, and audit event writes stay
outside the route layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.database import Organisation
from multi_tenant_saas_api.domain import (
    AuditAction,
    MembershipID,
    OrganisationID,
    OrganisationRole,
    Permission,
    UserID,
)
from multi_tenant_saas_api.observability import MetricsRecorder, NoOpMetricsRecorder
from multi_tenant_saas_api.repositories import MembershipRepository, OrganisationRepository
from multi_tenant_saas_api.services.audit import AuditService
from multi_tenant_saas_api.services.rbac import (
    CurrentPrincipal,
    OrganisationNotFoundError,
    RBACService,
)

_NON_SLUG_CHARACTERS = re.compile(r"[^a-z0-9]+")


class OrganisationAPIServiceError(ValueError):
    """Base class for safe organisation API workflow errors."""


class OrganisationSlugAlreadyExistsError(OrganisationAPIServiceError):
    """Raised when an organisation slug would violate tenant slug uniqueness."""


@dataclass(frozen=True, slots=True)
class PublicOrganisation:
    """Organisation data safe to return from public API workflows."""

    id: OrganisationID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OrganisationList:
    """Paginated organisation list for a current user."""

    items: list[PublicOrganisation]
    limit: int
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class CreatedOwnerMembership:
    """Membership created when a user creates an organisation tenant."""

    id: MembershipID
    organisation_id: OrganisationID
    user_id: UserID
    role: OrganisationRole
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CreatedOrganisation:
    """Organisation creation result including the creator's owner membership."""

    organisation: PublicOrganisation
    owner_membership: CreatedOwnerMembership


class OrganisationAPIService:
    """Service layer for organisation tenant endpoints."""

    __slots__ = ("_audit", "_memberships", "_metrics", "_organisations", "_rbac", "_session")

    def __init__(
        self,
        *,
        session: AsyncSession,
        rbac_service: RBACService,
        organisation_repository: OrganisationRepository | None = None,
        membership_repository: MembershipRepository | None = None,
        audit_service: AuditService | None = None,
        metrics_recorder: MetricsRecorder | None = None,
    ) -> None:
        """Initialise organisation workflows with repository collaborators."""

        self._session = session
        self._rbac = rbac_service
        self._organisations = organisation_repository or OrganisationRepository(session)
        self._memberships = membership_repository or MembershipRepository(session)
        self._metrics = metrics_recorder or NoOpMetricsRecorder()
        self._audit = audit_service or AuditService(
            session=session,
            metrics_recorder=self._metrics,
        )

    async def create_organisation(
        self,
        *,
        principal: CurrentPrincipal,
        name: str,
        slug: str | None,
    ) -> CreatedOrganisation:
        """Create an organisation and make the creator its owner."""

        requested_slug = _normalise_slug(slug) if slug is not None else _slug_from_name(name)
        existing_organisation = await self._organisations.get_by_slug(requested_slug)
        if existing_organisation is not None:
            raise OrganisationSlugAlreadyExistsError("organisation slug is already in use")

        try:
            organisation = await self._organisations.create(name=name, slug=requested_slug)
            owner_membership = await self._memberships.create(
                organisation_id=organisation.id,
                user_id=_uuid_from_user_id(principal.user_id),
                role=OrganisationRole.OWNER,
            )
            await self._audit.record_event(
                action=AuditAction.ORGANISATION_CREATED,
                organisation_id=organisation.id,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="organisation",
                target_id=organisation.id,
                metadata={},
            )
            await self._session.commit()
            self._metrics.record_organisation_created()
        except IntegrityError as exc:
            await self._session.rollback()
            raise OrganisationSlugAlreadyExistsError("organisation slug is already in use") from exc
        except Exception:
            await self._session.rollback()
            raise

        return CreatedOrganisation(
            organisation=_public_organisation_from_model(organisation),
            owner_membership=CreatedOwnerMembership(
                id=MembershipID(owner_membership.id),
                organisation_id=OrganisationID(owner_membership.organisation_id),
                user_id=UserID(owner_membership.user_id),
                role=owner_membership.role,
                created_at=owner_membership.created_at,
                updated_at=owner_membership.updated_at,
            ),
        )

    async def list_organisations(
        self,
        *,
        principal: CurrentPrincipal,
        limit: int,
        offset: int,
    ) -> OrganisationList:
        """List only organisations where the current user has a membership."""

        user_id = _uuid_from_user_id(principal.user_id)
        organisations = await self._organisations.list_for_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        total = await self._organisations.count_for_user(user_id)
        return OrganisationList(
            items=[_public_organisation_from_model(organisation) for organisation in organisations],
            limit=limit,
            offset=offset,
            total=total,
        )

    async def get_organisation(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
    ) -> PublicOrganisation:
        """Return an organisation after tenant membership and read checks."""

        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_id,
            required_permission=Permission.READ_ORGANISATION,
        )
        organisation = await self._organisations.get_by_id(
            _uuid_from_organisation_id(organisation_id)
        )
        if organisation is None:
            # The RBAC service already verified existence. This branch protects
            # against a concurrent delete between the permission check and read.
            raise OrganisationNotFoundError("organisation was not found")
        return _public_organisation_from_model(organisation)

    async def update_organisation(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        name: str | None,
        slug: str | None,
    ) -> PublicOrganisation:
        """Update organisation metadata after membership and permission checks."""

        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_id,
            required_permission=Permission.UPDATE_ORGANISATION,
        )
        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        organisation = await self._organisations.get_by_id(organisation_uuid)
        if organisation is None:
            raise OrganisationNotFoundError("organisation was not found")

        requested_slug = _normalise_slug(slug) if slug is not None else None
        if requested_slug is not None and requested_slug != organisation.slug:
            existing_organisation = await self._organisations.get_by_slug(requested_slug)
            if existing_organisation is not None:
                raise OrganisationSlugAlreadyExistsError("organisation slug is already in use")

        changed_fields = _provided_update_fields(name=name, slug=requested_slug)

        try:
            updated_organisation = await self._organisations.update(
                organisation,
                name=name,
                slug=requested_slug,
            )
            await self._audit.record_event(
                action=AuditAction.ORGANISATION_UPDATED,
                organisation_id=updated_organisation.id,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="organisation",
                target_id=updated_organisation.id,
                metadata={"changed_fields": changed_fields},
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise OrganisationSlugAlreadyExistsError("organisation slug is already in use") from exc
        except Exception:
            await self._session.rollback()
            raise

        return _public_organisation_from_model(updated_organisation)


def _public_organisation_from_model(organisation: Organisation) -> PublicOrganisation:
    """Convert a repository model to a secret-safe organisation DTO."""

    return PublicOrganisation(
        id=OrganisationID(organisation.id),
        name=organisation.name,
        slug=organisation.slug,
        created_at=organisation.created_at,
        updated_at=organisation.updated_at,
    )


def _uuid_from_user_id(user_id: UUID | UserID) -> UUID:
    """Return the runtime UUID value held by a typed user identifier."""

    return UUID(str(user_id))


def _uuid_from_organisation_id(organisation_id: UUID | OrganisationID) -> UUID:
    """Return the runtime UUID value held by a typed organisation identifier."""

    return UUID(str(organisation_id))


def _normalise_slug(slug: str) -> str:
    """Normalise an explicitly supplied slug before uniqueness checks."""

    return slug.strip().lower()


def _slug_from_name(name: str) -> str:
    """Derive a public-safe URL slug from an organisation name."""

    candidate = _NON_SLUG_CHARACTERS.sub("-", name.strip().lower()).strip("-")
    if len(candidate) < 3:
        candidate = f"{candidate}-org" if candidate else "org"
    candidate = candidate[:80].strip("-")
    if len(candidate) < 3:
        return "org"
    return candidate


def _provided_update_fields(*, name: str | None, slug: str | None) -> list[str]:
    """Return the non-secret metadata field names supplied in an update."""

    changed_fields: list[str] = []
    if name is not None:
        changed_fields.append("name")
    if slug is not None:
        changed_fields.append("slug")
    return changed_fields


__all__ = [
    "CreatedOrganisation",
    "CreatedOwnerMembership",
    "OrganisationAPIService",
    "OrganisationAPIServiceError",
    "OrganisationList",
    "OrganisationSlugAlreadyExistsError",
    "PublicOrganisation",
]
