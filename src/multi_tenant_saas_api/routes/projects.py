"""Organisation-scoped project endpoint routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from multi_tenant_saas_api.dependencies import get_current_principal, get_project_api_service
from multi_tenant_saas_api.domain import ProjectSortField, ProjectStatus, SortDirection
from multi_tenant_saas_api.schemas.common import PaginationMeta
from multi_tenant_saas_api.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from multi_tenant_saas_api.services import (
    CurrentPrincipal,
    OrganisationNotFoundError,
    PermissionDeniedError,
    TenantAccessDeniedError,
)
from multi_tenant_saas_api.services.projects import (
    ProjectAPIService,
    ProjectList,
    ProjectNotFoundError,
    PublicProject,
)


def create_project_router() -> APIRouter:
    """Create routes for organisation-scoped project workflows."""

    router = APIRouter(prefix="/orgs/{organisation_id}/projects", tags=["projects"])

    @router.post(
        "",
        response_model=ProjectResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create an organisation project",
    )
    async def create_project(
        organisation_id: UUID,
        payload: ProjectCreateRequest,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
    ) -> ProjectResponse:
        """Create a tenant-scoped project for member/admin/owner roles."""

        try:
            project = await project_service.create_project(
                principal=principal,
                organisation_id=organisation_id,
                name=payload.name,
                description=payload.description,
                status=payload.status,
            )
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _project_response(project)

    @router.get(
        "",
        response_model=ProjectListResponse,
        summary="List organisation projects",
    )
    async def list_projects(
        organisation_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
        name: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
        sort_by: Annotated[ProjectSortField, Query()] = ProjectSortField.CREATED_AT,
        sort_direction: Annotated[SortDirection, Query()] = SortDirection.DESC,
    ) -> ProjectListResponse:
        """Return tenant-scoped projects with pagination, filtering, and sorting."""

        try:
            projects = await project_service.list_projects(
                principal=principal,
                organisation_id=organisation_id,
                limit=limit,
                offset=offset,
                status=project_status,
                name_search=name,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _project_list_response(projects)

    @router.get(
        "/{project_id}",
        response_model=ProjectResponse,
        summary="Get one organisation project",
    )
    async def get_project(
        organisation_id: UUID,
        project_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
    ) -> ProjectResponse:
        """Return a tenant-scoped project after membership and read checks."""

        try:
            project = await project_service.get_project(
                principal=principal,
                organisation_id=organisation_id,
                project_id=project_id,
            )
        except ProjectNotFoundError as exc:
            raise _not_found("project was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _project_response(project)

    @router.patch(
        "/{project_id}",
        response_model=ProjectResponse,
        summary="Update an organisation project",
    )
    async def update_project(
        organisation_id: UUID,
        project_id: UUID,
        payload: ProjectUpdateRequest,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
    ) -> ProjectResponse:
        """Update a tenant-scoped project for member/admin/owner roles."""

        description_was_provided = "description" in payload.model_fields_set
        try:
            project = await project_service.update_project(
                principal=principal,
                organisation_id=organisation_id,
                project_id=project_id,
                name=payload.name,
                description=payload.description,
                description_was_provided=description_was_provided,
                status=payload.status,
            )
        except ProjectNotFoundError as exc:
            raise _not_found("project was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _project_response(project)

    @router.delete(
        "/{project_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete an organisation project",
    )
    async def delete_project(
        organisation_id: UUID,
        project_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
    ) -> Response:
        """Soft-delete a tenant-scoped project for member/admin/owner roles."""

        try:
            await project_service.delete_project(
                principal=principal,
                organisation_id=organisation_id,
                project_id=project_id,
            )
        except ProjectNotFoundError as exc:
            raise _not_found("project was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _project_response(project: PublicProject) -> ProjectResponse:
    """Convert service-layer project data to the API response schema."""

    return ProjectResponse.model_validate(project)


def _project_list_response(projects: ProjectList) -> ProjectListResponse:
    """Convert a service-layer project page to the API response schema."""

    items = [_project_response(project) for project in projects.items]
    return ProjectListResponse(
        items=items,
        pagination=PaginationMeta(
            limit=projects.limit,
            offset=projects.offset,
            total=projects.total,
            count=len(items),
        ),
    )


def _not_found(detail: str) -> HTTPException:
    """Build a safe not-found response."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    """Build a safe tenant access denied response."""

    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


__all__ = ["create_project_router"]
