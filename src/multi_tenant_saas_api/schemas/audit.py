"""Schemas for organisation-scoped audit events."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, JsonValue

from multi_tenant_saas_api.domain import APIKeyID, AuditAction, AuditEventID, OrganisationID, UserID
from multi_tenant_saas_api.schemas.common import APIModel, PaginationMeta


class AuditEventResponse(APIModel):
    """Append-only audit event response with secret-safe metadata."""

    id: AuditEventID
    organisation_id: OrganisationID | None
    actor_user_id: UserID | None
    actor_api_key_id: APIKeyID | None
    action: AuditAction
    target_type: str = Field(min_length=1, max_length=80)
    target_id: UUID | None
    metadata: dict[str, JsonValue]
    created_at: datetime


class AuditEventListResponse(APIModel):
    """Paginated audit event list response."""

    items: list[AuditEventResponse]
    pagination: PaginationMeta
