"""Repository for organisation membership persistence operations."""

from typing import cast
from uuid import UUID

from sqlalchemy import func, select

from multi_tenant_saas_api.database import OrganisationMembership
from multi_tenant_saas_api.domain import OrganisationRole
from multi_tenant_saas_api.repositories.base import BaseRepository


class MembershipRepository(BaseRepository):
    """Persist and retrieve organisation memberships."""

    async def create(
        self,
        *,
        organisation_id: UUID,
        user_id: UUID,
        role: OrganisationRole,
    ) -> OrganisationMembership:
        """Create a membership in an organisation tenant."""

        membership = OrganisationMembership(
            organisation_id=organisation_id,
            user_id=user_id,
            role=role,
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def get_for_user(
        self,
        *,
        organisation_id: UUID,
        user_id: UUID,
    ) -> OrganisationMembership | None:
        """Return one user's membership in an organisation, if present."""

        stmt = select(OrganisationMembership).where(
            OrganisationMembership.organisation_id == organisation_id,
            OrganisationMembership.user_id == user_id,
        )
        return cast(OrganisationMembership | None, await self._session.scalar(stmt))

    async def list_for_organisation(
        self,
        *,
        organisation_id: UUID,
        limit: int,
        offset: int = 0,
    ) -> list[OrganisationMembership]:
        """List memberships scoped to a single organisation tenant."""

        stmt = (
            select(OrganisationMembership)
            .where(OrganisationMembership.organisation_id == organisation_id)
            .order_by(OrganisationMembership.created_at.asc(), OrganisationMembership.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_for_user(self, user_id: UUID) -> list[OrganisationMembership]:
        """List all organisation memberships for a user."""

        stmt = (
            select(OrganisationMembership)
            .where(OrganisationMembership.user_id == user_id)
            .order_by(OrganisationMembership.created_at.asc(), OrganisationMembership.id.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def count_for_organisation(self, organisation_id: UUID) -> int:
        """Count memberships scoped to one organisation."""

        stmt = (
            select(func.count())
            .select_from(OrganisationMembership)
            .where(OrganisationMembership.organisation_id == organisation_id)
        )
        count = await self._session.scalar(stmt)
        return int(count or 0)

    async def count_owners(self, organisation_id: UUID) -> int:
        """Count owner memberships in an organisation."""

        stmt = (
            select(func.count())
            .select_from(OrganisationMembership)
            .where(
                OrganisationMembership.organisation_id == organisation_id,
                OrganisationMembership.role == OrganisationRole.OWNER,
            )
        )
        count = await self._session.scalar(stmt)
        return int(count or 0)

    async def has_other_owner(self, *, organisation_id: UUID, user_id: UUID) -> bool:
        """Return whether an organisation has an owner other than ``user_id``."""

        stmt = (
            select(func.count())
            .select_from(OrganisationMembership)
            .where(
                OrganisationMembership.organisation_id == organisation_id,
                OrganisationMembership.role == OrganisationRole.OWNER,
                OrganisationMembership.user_id != user_id,
            )
        )
        count = await self._session.scalar(stmt)
        return int(count or 0) > 0

    async def is_last_owner(self, *, organisation_id: UUID, user_id: UUID) -> bool:
        """Return whether ``user_id`` is the only owner in an organisation."""

        membership = await self.get_for_user(organisation_id=organisation_id, user_id=user_id)
        if membership is None or membership.role is not OrganisationRole.OWNER:
            return False
        return not await self.has_other_owner(organisation_id=organisation_id, user_id=user_id)

    async def update_role(
        self,
        membership: OrganisationMembership,
        *,
        role: OrganisationRole,
    ) -> OrganisationMembership:
        """Update a membership role."""

        membership.role = role
        await self._session.flush()
        return membership

    async def delete(self, membership: OrganisationMembership) -> None:
        """Delete a membership from its organisation."""

        await self._session.delete(membership)
        await self._session.flush()
