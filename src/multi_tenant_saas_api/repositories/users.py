"""Repository for user persistence operations."""

from typing import cast
from uuid import UUID

from sqlalchemy import select

from multi_tenant_saas_api.database import User
from multi_tenant_saas_api.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """Persist and retrieve application users."""

    async def create(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str,
        is_active: bool = True,
    ) -> User:
        """Create a user with hashed password storage only."""

        user = User(
            email=email,
            display_name=display_name,
            password_hash=password_hash,
            is_active=is_active,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Return a user by ID, if present."""

        stmt = select(User).where(User.id == user_id)
        return cast(User | None, await self._session.scalar(stmt))

    async def get_by_email(self, email: str) -> User | None:
        """Return a user by email address, if present."""

        stmt = select(User).where(User.email == email)
        return cast(User | None, await self._session.scalar(stmt))
