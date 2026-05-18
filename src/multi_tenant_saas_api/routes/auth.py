"""Authentication endpoint routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from multi_tenant_saas_api.dependencies import get_auth_api_service
from multi_tenant_saas_api.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from multi_tenant_saas_api.schemas.memberships import CurrentUserMembershipResponse
from multi_tenant_saas_api.schemas.users import UserResponse
from multi_tenant_saas_api.services import PasswordPolicyError
from multi_tenant_saas_api.services.auth_api import (
    AuthAPIService,
    CurrentUser,
    CurrentUserMembership,
    EmailAlreadyRegisteredError,
    InvalidBearerTokenError,
    InvalidCredentialsError,
    PublicUser,
)

_BEARER_SCHEME = HTTPBearer(auto_error=False)


def create_auth_router() -> APIRouter:
    """Create authentication routes."""

    router = APIRouter(tags=["auth"])

    @router.post(
        "/auth/register",
        response_model=RegisterResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Register a local demo user",
    )
    async def register_user(
        payload: RegisterRequest,
        auth_service: Annotated[AuthAPIService, Depends(get_auth_api_service)],
    ) -> RegisterResponse:
        """Register a user without returning password hashes or raw credentials."""

        try:
            user = await auth_service.register_user(
                email=str(payload.email),
                password=payload.password,
                display_name=payload.display_name,
            )
        except EmailAlreadyRegisteredError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="email is already registered",
            ) from exc
        except PasswordPolicyError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        return RegisterResponse(user=_user_response(user))

    @router.post(
        "/auth/login",
        response_model=LoginResponse,
        summary="Login with local demo credentials",
    )
    async def login_user(
        payload: LoginRequest,
        auth_service: Annotated[AuthAPIService, Depends(get_auth_api_service)],
    ) -> LoginResponse:
        """Return a bearer access token for valid email/password credentials."""

        try:
            access_token = await auth_service.login_user(
                email=str(payload.email),
                password=payload.password,
            )
        except InvalidCredentialsError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid email or password",
            ) from exc

        return LoginResponse(
            access_token=access_token.token,
            token_type="bearer",
            expires_in_seconds=access_token.expires_in_seconds,
        )

    @router.get(
        "/me",
        response_model=CurrentUserResponse,
        summary="Get the current authenticated user",
    )
    async def get_me(
        bearer_token: Annotated[str, Depends(_require_bearer_token)],
        auth_service: Annotated[AuthAPIService, Depends(get_auth_api_service)],
    ) -> CurrentUserResponse:
        """Return the current user and organisation memberships."""

        try:
            current_user = await auth_service.get_current_user(bearer_token=bearer_token)
        except InvalidBearerTokenError as exc:
            raise _unauthorized("invalid or expired access token") from exc

        return _current_user_response(current_user)

    return router


def _require_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER_SCHEME)],
) -> str:
    """Extract a bearer token string without validating the token in the route layer."""

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized("authentication required")
    return credentials.credentials


def _unauthorized(detail: str) -> HTTPException:
    """Build a bearer-auth 401 response."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _user_response(user: PublicUser) -> UserResponse:
    """Convert service-layer public user data to the API response schema."""

    return UserResponse.model_validate(user)


def _current_user_membership_response(
    membership: CurrentUserMembership,
) -> CurrentUserMembershipResponse:
    """Convert a service-layer membership summary to the API response schema."""

    return CurrentUserMembershipResponse.model_validate(membership)


def _current_user_response(current_user: CurrentUser) -> CurrentUserResponse:
    """Convert service-layer current-user data to the API response schema."""

    return CurrentUserResponse(
        user=_user_response(current_user.user),
        memberships=[
            _current_user_membership_response(membership) for membership in current_user.memberships
        ],
    )


__all__ = ["create_auth_router"]
