"""Organisation-scoped project endpoint routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from multi_tenant_saas_api.dependencies import (
    get_idempotency_service,
    get_project_api_service,
    get_project_principal,
)
from multi_tenant_saas_api.domain import ProjectSortField, ProjectStatus, SortDirection
from multi_tenant_saas_api.routes._idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    idempotency_conflict_response,
    idempotency_replay_response,
)
from multi_tenant_saas_api.schemas.common import PaginationMeta
from multi_tenant_saas_api.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from multi_tenant_saas_api.services import (
    IdempotencyConflictError,
    IdempotencyService,
    OrganisationNotFoundError,
    PermissionDeniedError,
    ProjectPrincipal,
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
        request: Request,
        principal: Annotated[ProjectPrincipal, Depends(get_project_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
        idempotency_service: Annotated[
            IdempotencyService,
            Depends(get_idempotency_service),
        ],
        idempotency_key: Annotated[
            str | None,
            Header(alias=IDEMPOTENCY_KEY_HEADER, min_length=1, max_length=255),
        ] = None,
    ) -> ProjectResponse | JSONResponse:
        """Create a tenant-scoped project for users with write access or API keys."""

        try:
            if idempotency_key is not None:
                await project_service.ensure_can_create_project(
                    principal=principal,
                    organisation_id=organisation_id,
                )
            idempotency = await idempotency_service.start_request(
                key=idempotency_key,
                principal=principal,
                method=request.method,
                path=request.url.path,
                request_body=payload,
                organisation_id=organisation_id,
            )
        except IdempotencyConflictError as exc:
            raise idempotency_conflict_response() from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc
        if idempotency.replay is not None:
            return idempotency_replay_response(idempotency.replay)

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

        response = _project_response(project)
        await idempotency_service.store_response(
            context=idempotency.context,
            response_status_code=status.HTTP_201_CREATED,
            response_body=response.model_dump(mode="json"),
        )
        return response

    @router.get(
        "",
        response_model=ProjectListResponse,
        summary="List organisation projects",
    )
    async def list_projects(
        organisation_id: UUID,
        principal: Annotated[ProjectPrincipal, Depends(get_project_principal)],
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
        principal: Annotated[ProjectPrincipal, Depends(get_project_principal)],
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
        principal: Annotated[ProjectPrincipal, Depends(get_project_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
    ) -> ProjectResponse:
        """Update a tenant-scoped project for users with write access or API keys."""

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
        principal: Annotated[ProjectPrincipal, Depends(get_project_principal)],
        project_service: Annotated[ProjectAPIService, Depends(get_project_api_service)],
    ) -> Response:
        """Soft-delete a tenant-scoped project for users with write access or API keys."""

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
