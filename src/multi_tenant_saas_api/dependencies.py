"""FastAPI dependency helpers for application services."""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.services import (
    AccessTokenService,
    CurrentPrincipal,
    PasswordHashingService,
    PrincipalResolutionError,
    RBACService,
)
from multi_tenant_saas_api.services.auth_api import AuthAPIService
from multi_tenant_saas_api.services.memberships import MembershipAPIService
from multi_tenant_saas_api.services.organisations import OrganisationAPIService

_BEARER_SCHEME = HTTPBearer(auto_error=False)


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


def get_rbac_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
) -> RBACService:
    """Build the RBAC and tenant-context service for one request."""

    return RBACService(
        session=session,
        token_service=AccessTokenService.from_settings(settings),
    )


def get_organisation_api_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
) -> OrganisationAPIService:
    """Build the organisation workflow service for one request."""

    return OrganisationAPIService(session=session, rbac_service=rbac_service)


def get_membership_api_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
) -> MembershipAPIService:
    """Build the membership management workflow service for one request."""

    return MembershipAPIService(session=session, rbac_service=rbac_service)


def require_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER_SCHEME)],
) -> str:
    """Extract a bearer token string without logging or exposing token material."""

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized("authentication required")
    return credentials.credentials


async def get_current_principal(
    bearer_token: Annotated[str, Depends(require_bearer_token)],
    rbac_service: Annotated[RBACService, Depends(get_rbac_service)],
) -> CurrentPrincipal:
    """Resolve the current active principal for protected business routes."""

    try:
        return await rbac_service.resolve_current_principal(bearer_token=bearer_token)
    except PrincipalResolutionError as exc:
        raise _unauthorized("invalid or expired access token") from exc


def _unauthorized(detail: str) -> HTTPException:
    """Build a bearer-auth 401 response."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


__all__ = [
    "get_auth_api_service",
    "get_current_principal",
    "get_membership_api_service",
    "get_organisation_api_service",
    "get_rbac_service",
    "get_session",
    "get_settings_from_app",
    "require_bearer_token",
]
