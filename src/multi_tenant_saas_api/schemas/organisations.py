"""Schemas for organisation tenant APIs."""

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from multi_tenant_saas_api.domain import OrganisationID
from multi_tenant_saas_api.schemas.common import APIModel, PaginationMeta

_ORGANISATION_SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class OrganisationCreateRequest(APIModel):
    """Request to create an organisation tenant."""

    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=80,
        pattern=_ORGANISATION_SLUG_PATTERN,
    )


class OrganisationUpdateRequest(APIModel):
    """Request to update organisation metadata."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=80,
        pattern=_ORGANISATION_SLUG_PATTERN,
    )

    @model_validator(mode="after")
    def require_a_change(self) -> Self:
        """Reject empty organisation PATCH payloads."""

        if self.name is None and self.slug is None:
            msg = "at least one organisation field must be provided"
            raise ValueError(msg)
        return self


class OrganisationResponse(APIModel):
    """Organisation tenant response."""

    id: OrganisationID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class OrganisationListResponse(APIModel):
    """Paginated organisation list response."""

    items: list[OrganisationResponse]
    pagination: PaginationMeta
