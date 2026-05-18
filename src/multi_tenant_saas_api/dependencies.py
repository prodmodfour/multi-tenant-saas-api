"""FastAPI dependency helpers for application services."""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.services import AccessTokenService, PasswordHashingService
from multi_tenant_saas_api.services.auth_api import AuthAPIService


def get_settings_from_app(request: Request) -> Settings:
    """Return the immutable settings object attached to the FastAPI app."""

    return cast(Settings, request.app.state.settings)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield one SQLAlchemy session for a request-scoped unit of work."""

    session_factory = cast(
        async_sessionmaker[AsyncSession],
        request.app.state.session_factory,
    )
    async with session_factory() as session:
        yield session


def get_auth_api_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> AuthAPIService:
    """Build the authentication workflow service for one request."""

    return AuthAPIService(
        session=session,
        password_service=PasswordHashingService.from_settings(settings),
        token_service=AccessTokenService.from_settings(settings),
    )


__all__ = ["get_auth_api_service", "get_session", "get_settings_from_app"]
