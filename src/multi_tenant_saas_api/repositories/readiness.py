"""Repository helpers for dependency readiness checks."""

from sqlalchemy import text

from multi_tenant_saas_api.repositories.base import BaseRepository


class DatabaseReadinessRepository(BaseRepository):
    """Run minimal database dependency checks through SQLAlchemy."""

    async def check_postgresql(self) -> None:
        """Execute a minimal PostgreSQL round trip for readiness checks."""

        await self._session.execute(text("SELECT 1"))


__all__ = ["DatabaseReadinessRepository"]
