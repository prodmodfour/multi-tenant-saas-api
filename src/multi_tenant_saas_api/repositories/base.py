"""Common repository infrastructure."""

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Base class for repositories that own SQLAlchemy session access."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
