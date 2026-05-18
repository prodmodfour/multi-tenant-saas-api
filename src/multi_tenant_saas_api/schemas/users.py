"""User-facing schemas that never expose password hashes."""

from datetime import datetime

from pydantic import EmailStr, Field

from multi_tenant_saas_api.domain import UserID
from multi_tenant_saas_api.schemas.common import APIModel


class UserSummary(APIModel):
    """Small user representation suitable for embedding in other responses."""

    id: UserID
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    is_active: bool


class UserResponse(UserSummary):
    """Full public user response."""

    created_at: datetime
    updated_at: datetime
