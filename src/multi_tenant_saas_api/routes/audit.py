"""Organisation-scoped audit event endpoint routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from multi_tenant_saas_api.dependencies import get_audit_service, get_current_principal
from multi_tenant_saas_api.schemas.audit import AuditEventListResponse, AuditEventResponse
from multi_tenant_saas_api.schemas.common import PaginationMeta
from multi_tenant_saas_api.services import (
    CurrentPrincipal,
    OrganisationNotFoundError,
    PermissionDeniedError,
    TenantAccessDeniedError,
)
from multi_tenant_saas_api.services.audit import AuditEventPage, AuditService, PublicAuditEvent


def create_audit_router() -> APIRouter:
    """Create routes for organisation audit log reads."""

    router = APIRouter(prefix="/orgs/{organisation_id}/audit-events", tags=["audit"])

    @router.get(
        "",
        response_model=AuditEventListResponse,
        summary="List organisation audit events",
    )
    async def list_audit_events(
        organisation_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        audit_service: Annotated[AuditService, Depends(get_audit_service)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> AuditEventListResponse:
        """Return append-only audit events for owner/admin members."""

        try:
            audit_events = await audit_service.list_organisation_events(
                principal=principal,
                organisation_id=organisation_id,
                limit=limit,
                offset=offset,
            )
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _audit_event_list_response(audit_events)

    return router


def _audit_event_response(audit_event: PublicAuditEvent) -> AuditEventResponse:
    """Convert a service-layer audit event to the API response schema."""

    return AuditEventResponse.model_validate(audit_event)


def _audit_event_list_response(audit_events: AuditEventPage) -> AuditEventListResponse:
    """Convert a service-layer audit event page to the API response schema."""

    items = [_audit_event_response(audit_event) for audit_event in audit_events.items]
    return AuditEventListResponse(
        items=items,
        pagination=PaginationMeta(
            limit=audit_events.limit,
            offset=audit_events.offset,
            total=audit_events.total,
            count=len(items),
        ),
    )


def _not_found(detail: str) -> HTTPException:
    """Build a safe not-found response."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    """Build a safe tenant access denied response."""

    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


__all__ = ["create_audit_router"]
