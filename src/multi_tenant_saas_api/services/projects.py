"""Organisation-scoped project API workflows.

This module owns project creation, listing, detail, update, and soft-delete
business logic. It keeps HTTP routes thin while enforcing tenant membership,
RBAC, tenant-scoped repository calls, transaction handling, and secret-safe audit
event creation in the service layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.database import Project
from multi_tenant_saas_api.domain import (
    AuditAction,
    OrganisationID,
    Permission,
    ProjectID,
    ProjectSortField,
    ProjectStatus,
    SortDirection,
    UserID,
)
from multi_tenant_saas_api.repositories import AuditEventRepository, ProjectRepository
from multi_tenant_saas_api.services.rbac import CurrentPrincipal, RBACService


class ProjectAPIServiceError(ValueError):
    """Base class for safe project API workflow errors."""


class ProjectNotFoundError(ProjectAPIServiceError):
    """Raised when a requested tenant-scoped project does not exist."""


@dataclass(frozen=True, slots=True)
class PublicProject:
    """Project data safe to return from public API workflows."""

    id: ProjectID
    organisation_id: OrganisationID
    name: str
    status: ProjectStatus
    description: str | None
    created_by_user_id: UserID | None
    updated_by_user_id: UserID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectList:
    """Paginated project list for one organisation tenant."""

    items: list[PublicProject]
    limit: int
    offset: int
    total: int


class ProjectAPIService:
    """Service layer for organisation-scoped project endpoints."""

    __slots__ = ("_audit_events", "_projects", "_rbac", "_session")

    def __init__(
        self,
        *,
        session: AsyncSession,
        rbac_service: RBACService,
        project_repository: ProjectRepository | None = None,
        audit_event_repository: AuditEventRepository | None = None,
    ) -> None:
        """Initialise project workflows with repository collaborators."""

        self._session = session
        self._rbac = rbac_service
        self._projects = project_repository or ProjectRepository(session)
        self._audit_events = audit_event_repository or AuditEventRepository(session)

    async def create_project(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        name: str,
        description: str | None,
        status: ProjectStatus,
    ) -> PublicProject:
        """Create a project after tenant and write-project checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.WRITE_PROJECTS,
        )

        try:
            project = await self._projects.create(
                organisation_id=organisation_uuid,
                name=name,
                status=status,
                description=description,
                created_by_user_id=_uuid_from_user_id(principal.user_id),
            )
            await self._audit_events.create(
                action=AuditAction.PROJECT_CREATED,
                organisation_id=organisation_uuid,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="project",
                target_id=project.id,
                event_metadata={"project_name": project.name, "status": project.status.value},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return _public_project_from_model(project)

    async def list_projects(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        limit: int,
        offset: int,
        status: ProjectStatus | None,
        name_search: str | None,
        sort_by: ProjectSortField,
        sort_direction: SortDirection,
    ) -> ProjectList:
        """List projects after tenant and read-project checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.READ_PROJECTS,
        )
        projects = await self._projects.list_for_organisation(
            organisation_id=organisation_uuid,
            limit=limit,
            offset=offset,
            status=status,
            name_search=name_search,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
        total = await self._projects.count_for_organisation(
            organisation_id=organisation_uuid,
            status=status,
            name_search=name_search,
        )
        return ProjectList(
            items=[_public_project_from_model(project) for project in projects],
            limit=limit,
            offset=offset,
            total=total,
        )

    async def get_project(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        project_id: UUID | ProjectID,
    ) -> PublicProject:
        """Return one project after tenant and read-project checks."""

        project = await self._get_authorised_project(
            principal=principal,
            organisation_id=organisation_id,
            project_id=project_id,
            required_permission=Permission.READ_PROJECTS,
        )
        return _public_project_from_model(project)

    async def update_project(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        project_id: UUID | ProjectID,
        name: str | None,
        description: str | None,
        description_was_provided: bool,
        status: ProjectStatus | None,
    ) -> PublicProject:
        """Update one project after tenant and write-project checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        project = await self._get_authorised_project(
            principal=principal,
            organisation_id=organisation_uuid,
            project_id=project_id,
            required_permission=Permission.WRITE_PROJECTS,
        )
        changed_fields = _provided_update_fields(
            name=name,
            description_was_provided=description_was_provided,
            status=status,
        )

        try:
            if description_was_provided:
                updated_project = await self._projects.update(
                    project,
                    name=name,
                    description=description,
                    status=status,
                    updated_by_user_id=_uuid_from_user_id(principal.user_id),
                )
            else:
                updated_project = await self._projects.update(
                    project,
                    name=name,
                    status=status,
                    updated_by_user_id=_uuid_from_user_id(principal.user_id),
                )
            await self._audit_events.create(
                action=AuditAction.PROJECT_UPDATED,
                organisation_id=organisation_uuid,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="project",
                target_id=updated_project.id,
                event_metadata={"changed_fields": changed_fields},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return _public_project_from_model(updated_project)

    async def delete_project(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        project_id: UUID | ProjectID,
    ) -> None:
        """Soft-delete one project after tenant and write-project checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        project = await self._get_authorised_project(
            principal=principal,
            organisation_id=organisation_uuid,
            project_id=project_id,
            required_permission=Permission.WRITE_PROJECTS,
        )
        project_name = project.name

        try:
            deleted_project = await self._projects.delete(
                project,
                updated_by_user_id=_uuid_from_user_id(principal.user_id),
            )
            await self._audit_events.create(
                action=AuditAction.PROJECT_DELETED,
                organisation_id=organisation_uuid,
                actor_user_id=_uuid_from_user_id(principal.user_id),
                target_type="project",
                target_id=deleted_project.id,
                event_metadata={"project_name": project_name},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

    async def _get_authorised_project(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        project_id: UUID | ProjectID,
        required_permission: Permission,
    ) -> Project:
        """Return a tenant-scoped project after checking the requested permission."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=required_permission,
        )
        project = await self._projects.get_by_id(
            organisation_id=organisation_uuid,
            project_id=_uuid_from_project_id(project_id),
        )
        if project is None:
            raise ProjectNotFoundError("project was not found")
        return project


def _public_project_from_model(project: Project) -> PublicProject:
    """Convert a repository project model to a secret-safe DTO."""

    return PublicProject(
        id=ProjectID(project.id),
        organisation_id=OrganisationID(project.organisation_id),
        name=project.name,
        status=project.status,
        description=project.description,
        created_by_user_id=UserID(project.created_by_user_id)
        if project.created_by_user_id is not None
        else None,
        updated_by_user_id=UserID(project.updated_by_user_id)
        if project.updated_by_user_id is not None
        else None,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _provided_update_fields(
    *,
    name: str | None,
    description_was_provided: bool,
    status: ProjectStatus | None,
) -> list[str]:
    """Return the non-secret metadata field names supplied in a project update."""

    changed_fields: list[str] = []
    if name is not None:
        changed_fields.append("name")
    if description_was_provided:
        changed_fields.append("description")
    if status is not None:
        changed_fields.append("status")
    return changed_fields


def _uuid_from_user_id(user_id: UUID | UserID) -> UUID:
    """Return the runtime UUID value held by a typed user identifier."""

    return UUID(str(user_id))


def _uuid_from_organisation_id(organisation_id: UUID | OrganisationID) -> UUID:
    """Return the runtime UUID value held by a typed organisation identifier."""

    return UUID(str(organisation_id))


def _uuid_from_project_id(project_id: UUID | ProjectID) -> UUID:
    """Return the runtime UUID value held by a typed project identifier."""

    return UUID(str(project_id))


__all__ = [
    "ProjectAPIService",
    "ProjectAPIServiceError",
    "ProjectList",
    "ProjectNotFoundError",
    "PublicProject",
]
