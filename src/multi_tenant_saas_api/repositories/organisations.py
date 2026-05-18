"""Repository for organisation tenant persistence operations."""

from typing import cast
from uuid import UUID

from sqlalchemy import func, select

from multi_tenant_saas_api.database import Organisation, OrganisationMembership
from multi_tenant_saas_api.repositories.base import BaseRepository


class OrganisationRepository(BaseRepository):
    """Persist and retrieve organisation tenants."""

    async def create(self, *, name: str, slug: str) -> Organisation:
        """Create an organisation tenant."""

        organisation = Organisation(name=name, slug=slug)
        self._session.add(organisation)
        await self._session.flush()
        return organisation

    async def get_by_id(self, organisation_id: UUID) -> Organisation | None:
        """Return an organisation by ID, if present."""

        stmt = select(Organisation).where(Organisation.id == organisation_id)
        return cast(Organisation | None, await self._session.scalar(stmt))

    async def get_by_slug(self, slug: str) -> Organisation | None:
        """Return an organisation by unique slug, if present."""

        stmt = select(Organisation).where(Organisation.slug == slug)
        return cast(Organisation | None, await self._session.scalar(stmt))

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        limit: int,
        offset: int = 0,
    ) -> list[Organisation]:
        """List organisations where ``user_id`` has a membership."""

        stmt = (
            select(Organisation)
            .join(
                OrganisationMembership,
                OrganisationMembership.organisation_id == Organisation.id,
            )
            .where(OrganisationMembership.user_id == user_id)
            .order_by(Organisation.name.asc(), Organisation.id.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def count_for_user(self, user_id: UUID) -> int:
        """Count organisations where ``user_id`` has a membership."""

        stmt = (
            select(func.count())
            .select_from(OrganisationMembership)
            .where(OrganisationMembership.user_id == user_id)
        )
        count = await self._session.scalar(stmt)
        return int(count or 0)

    async def update(
        self,
        organisation: Organisation,
        *,
        name: str | None = None,
        slug: str | None = None,
    ) -> Organisation:
        """Update mutable organisation metadata."""

        if name is not None:
            organisation.name = name
        if slug is not None:
            organisation.slug = slug
        await self._session.flush()
        return organisation
