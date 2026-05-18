"""Schemas for organisation-scoped API key management."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from multi_tenant_saas_api.domain import APIKeyID, OrganisationID, UserID
from multi_tenant_saas_api.schemas.common import APIModel, PaginationMeta


class APIKeyCreateRequest(APIModel):
    """Request to create a labelled organisation API key."""

    name: str = Field(min_length=1, max_length=120)


class APIKeyResponse(APIModel):
    """API key metadata response that never includes raw key material or hashes."""

    id: APIKeyID
    organisation_id: OrganisationID
    name: str
    key_prefix: str = Field(min_length=4, max_length=16)
    created_by_user_id: UserID | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


class APIKeyCreateResponse(APIModel):
    """One-time API key creation response.

    ``raw_key`` is intentionally present only in this response schema. List,
    detail, and revoke responses expose metadata only.
    """

    api_key: APIKeyResponse
    raw_key: str = Field(min_length=1)


class APIKeyListResponse(APIModel):
    """Paginated API key metadata list response."""

    items: list[APIKeyResponse]
    pagination: PaginationMeta


class APIKeyRevokeResponse(APIModel):
    """Response returned after an API key has been revoked."""

    id: APIKeyID
    organisation_id: OrganisationID
    status: Literal["revoked"] = "revoked"
    revoked_at: datetime
