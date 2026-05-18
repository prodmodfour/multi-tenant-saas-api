"""Schemas for organisation-scoped project APIs."""

from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from multi_tenant_saas_api.domain import OrganisationID, ProjectID, ProjectStatus, UserID
from multi_tenant_saas_api.schemas.common import APIModel, PaginationMeta

_PROJECT_UPDATE_FIELDS = frozenset({"name", "description", "status"})


class ProjectCreateRequest(APIModel):
    """Request to create a project inside an organisation tenant."""

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    status: ProjectStatus = ProjectStatus.ACTIVE


class ProjectUpdateRequest(APIModel):
    """Request to update project metadata or lifecycle state."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    status: ProjectStatus | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> Self:
        """Reject empty project PATCH payloads."""

        if self.model_fields_set.isdisjoint(_PROJECT_UPDATE_FIELDS):
            msg = "at least one project field must be provided"
            raise ValueError(msg)
        return self


class ProjectResponse(APIModel):
    """Project response scoped to its owning organisation."""

    id: ProjectID
    organisation_id: OrganisationID
    name: str
    status: ProjectStatus
    description: str | None
    created_by_user_id: UserID | None
    updated_by_user_id: UserID | None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(APIModel):
    """Paginated project list response."""

    items: list[ProjectResponse]
    pagination: PaginationMeta
