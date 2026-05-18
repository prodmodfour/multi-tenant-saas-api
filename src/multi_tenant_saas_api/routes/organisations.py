"""Organisation tenant endpoint routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from multi_tenant_saas_api.dependencies import get_current_principal, get_organisation_api_service
from multi_tenant_saas_api.schemas.common import PaginationMeta
from multi_tenant_saas_api.schemas.organisations import (
    OrganisationCreateRequest,
    OrganisationListResponse,
    OrganisationResponse,
    OrganisationUpdateRequest,
)
from multi_tenant_saas_api.services import (
    CurrentPrincipal,
    OrganisationNotFoundError,
    PermissionDeniedError,
    TenantAccessDeniedError,
)
from multi_tenant_saas_api.services.organisations import (
    CreatedOrganisation,
    OrganisationAPIService,
    OrganisationList,
    OrganisationSlugAlreadyExistsError,
    PublicOrganisation,
)


def create_organisation_router() -> APIRouter:
    """Create routes for organisation tenant workflows."""

    router = APIRouter(prefix="/orgs", tags=["organisations"])

    @router.post(
        "",
        response_model=OrganisationResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create an organisation tenant",
    )
    async def create_organisation(
        payload: OrganisationCreateRequest,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        organisation_service: Annotated[
            OrganisationAPIService,
            Depends(get_organisation_api_service),
        ],
    ) -> OrganisationResponse:
        """Create an organisation and grant the creator the owner role."""

        try:
            created = await organisation_service.create_organisation(
                principal=principal,
                name=payload.name,
                slug=payload.slug,
            )
        except OrganisationSlugAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="organisation slug is already in use",
            ) from exc

        return _created_organisation_response(created)

    @router.get(
        "",
        response_model=OrganisationListResponse,
        summary="List organisations for the current user",
    )
    async def list_organisations(
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        organisation_service: Annotated[
            OrganisationAPIService,
            Depends(get_organisation_api_service),
        ],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> OrganisationListResponse:
        """Return only organisations where the principal is a member."""

        organisations = await organisation_service.list_organisations(
            principal=principal,
            limit=limit,
            offset=offset,
        )
        return _organisation_list_response(organisations)

    @router.get(
        "/{organisation_id}",
        response_model=OrganisationResponse,
        summary="Get one organisation tenant",
    )
    async def get_organisation(
        organisation_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        organisation_service: Annotated[
            OrganisationAPIService,
            Depends(get_organisation_api_service),
        ],
    ) -> OrganisationResponse:
        """Return organisation metadata after tenant membership checks."""

        try:
            organisation = await organisation_service.get_organisation(
                principal=principal,
                organisation_id=organisation_id,
            )
        except OrganisationNotFoundError as exc:
            raise _not_found() from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _organisation_response(organisation)

    @router.patch(
        "/{organisation_id}",
        response_model=OrganisationResponse,
        summary="Update organisation metadata",
    )
    async def update_organisation(
        organisation_id: UUID,
        payload: OrganisationUpdateRequest,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        organisation_service: Annotated[
            OrganisationAPIService,
            Depends(get_organisation_api_service),
        ],
    ) -> OrganisationResponse:
        """Update organisation metadata for owner/admin members."""

        try:
            organisation = await organisation_service.update_organisation(
                principal=principal,
                organisation_id=organisation_id,
                name=payload.name,
                slug=payload.slug,
            )
        except OrganisationSlugAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="organisation slug is already in use",
            ) from exc
        except OrganisationNotFoundError as exc:
            raise _not_found() from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _organisation_response(organisation)

    return router


def _created_organisation_response(created: CreatedOrganisation) -> OrganisationResponse:
    """Return the created organisation without exposing membership internals."""

    return _organisation_response(created.organisation)


def _organisation_response(organisation: PublicOrganisation) -> OrganisationResponse:
    """Convert service-layer organisation data to the API response schema."""

    return OrganisationResponse.model_validate(organisation)


def _organisation_list_response(organisations: OrganisationList) -> OrganisationListResponse:
    """Convert a service-layer organisation page to the API response schema."""

    items = [_organisation_response(organisation) for organisation in organisations.items]
    return OrganisationListResponse(
        items=items,
        pagination=PaginationMeta(
            limit=organisations.limit,
            offset=organisations.offset,
            total=organisations.total,
            count=len(items),
        ),
    )


def _not_found() -> HTTPException:
    """Build a safe organisation not-found response."""

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="organisation was not found",
    )


def _forbidden(detail: str) -> HTTPException:
    """Build a safe tenant access denied response."""

    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


__all__ = ["create_organisation_router"]
