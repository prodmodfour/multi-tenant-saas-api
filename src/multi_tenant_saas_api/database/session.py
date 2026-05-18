"""Async SQLAlchemy engine and session factory helpers."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from multi_tenant_saas_api.config import Settings, get_settings


def create_database_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create an async SQLAlchemy engine from application settings."""

    app_settings = settings or get_settings()
    return create_async_engine(app_settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory bound to ``engine``."""

    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def iter_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield one async database session for dependency-injection use."""

    async with session_factory() as session:
        yield session


__all__ = ["create_database_engine", "create_session_factory", "iter_session"]
