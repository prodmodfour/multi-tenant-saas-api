"""Repository for organisation-scoped API key metadata operations."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select

from multi_tenant_saas_api.database import APIKey
from multi_tenant_saas_api.repositories.base import BaseRepository


class APIKeyRepository(BaseRepository):
    """Persist and retrieve hashed API key metadata."""

    async def create(
        self,
        *,
        organisation_id: UUID,
        name: str,
        key_prefix: str,
        key_hash: str,
        created_by_user_id: UUID | None = None,
    ) -> APIKey:
        """Create API key metadata with hashed key material only."""

        api_key = APIKey(
            organisation_id=organisation_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(api_key)
        await self._session.flush()
        return api_key

    async def get_by_id(
        self,
        *,
        organisation_id: UUID,
        api_key_id: UUID,
    ) -> APIKey | None:
        """Return API key metadata by ID while enforcing organisation scope."""

        stmt = select(APIKey).where(
            APIKey.organisation_id == organisation_id,
            APIKey.id == api_key_id,
        )
        return cast(APIKey | None, await self._session.scalar(stmt))

    async def get_active_by_hash(self, key_hash: str) -> APIKey | None:
        """Return the active API key that matches ``key_hash``, if any."""

        stmt = select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.revoked_at.is_(None),
        )
        return cast(APIKey | None, await self._session.scalar(stmt))

    async def list_for_organisation(
        self,
        *,
        organisation_id: UUID,
        limit: int,
        offset: int = 0,
        include_revoked: bool = True,
    ) -> list[APIKey]:
        """List API key metadata scoped to one organisation tenant."""

        stmt = select(APIKey).where(APIKey.organisation_id == organisation_id)
        if not include_revoked:
            stmt = stmt.where(APIKey.revoked_at.is_(None))
        stmt = stmt.order_by(APIKey.created_at.desc(), APIKey.id.desc()).limit(limit).offset(offset)
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def count_for_organisation(
        self,
        *,
        organisation_id: UUID,
        include_revoked: bool = True,
    ) -> int:
        """Count API key metadata records scoped to one organisation."""

        stmt = (
            select(func.count())
            .select_from(APIKey)
            .where(APIKey.organisation_id == organisation_id)
        )
        if not include_revoked:
            stmt = stmt.where(APIKey.revoked_at.is_(None))
        count = await self._session.scalar(stmt)
        return int(count or 0)

    async def revoke(
        self,
        api_key: APIKey,
        *,
        revoked_at: datetime | None = None,
    ) -> APIKey:
        """Revoke an API key without exposing raw key material."""

        api_key.revoked_at = revoked_at or datetime.now(UTC)
        await self._session.flush()
        return api_key

    async def update_last_used(
        self,
        api_key: APIKey,
        *,
        last_used_at: datetime | None = None,
    ) -> APIKey:
        """Record successful API key use without storing raw key material."""

        api_key.last_used_at = last_used_at or datetime.now(UTC)
        await self._session.flush()
        return api_key
