"""Schemas for local demo authentication endpoints."""

from typing import Literal

from pydantic import EmailStr, Field, SecretStr

from multi_tenant_saas_api.schemas.common import APIModel
from multi_tenant_saas_api.schemas.memberships import CurrentUserMembershipResponse
from multi_tenant_saas_api.schemas.users import UserResponse

MIN_PASSWORD_LENGTH = 12


class RegisterRequest(APIModel):
    """Registration request for email/password demo authentication."""

    email: EmailStr
    password: SecretStr = Field(min_length=MIN_PASSWORD_LENGTH, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)


class RegisterResponse(APIModel):
    """Registration response containing only public user fields."""

    user: UserResponse


class LoginRequest(APIModel):
    """Login request for local demo authentication."""

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=256)


class LoginResponse(APIModel):
    """Bearer token response returned after successful login."""

    access_token: str = Field(min_length=1)
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int = Field(gt=0)


class CurrentUserResponse(APIModel):
    """Current authenticated user and organisation memberships."""

    user: UserResponse
    memberships: list[CurrentUserMembershipResponse]
