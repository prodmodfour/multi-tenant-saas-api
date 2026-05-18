"""Repository for organisation-scoped project persistence operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select

from multi_tenant_saas_api.database import Project
from multi_tenant_saas_api.domain import ProjectStatus
from multi_tenant_saas_api.repositories.base import BaseRepository


class _UnsetValue:
    """Sentinel type for optional update fields where ``None`` is meaningful."""


_UNSET = _UnsetValue()


class ProjectRepository(BaseRepository):
    """Persist and retrieve projects inside an organisation tenant."""

    async def create(
        self,
        *,
        organisation_id: UUID,
        name: str,
        status: ProjectStatus = ProjectStatus.ACTIVE,
        description: str | None = None,
        created_by_user_id: UUID | None = None,
    ) -> Project:
        """Create a project scoped to one organisation."""

        project = Project(
            organisation_id=organisation_id,
            name=name,
            status=status,
            description=description,
            created_by_user_id=created_by_user_id,
            updated_by_user_id=created_by_user_id,
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def get_by_id(
        self,
        *,
        organisation_id: UUID,
        project_id: UUID,
        include_deleted: bool = False,
    ) -> Project | None:
        """Return a project by ID while enforcing organisation scope."""

        stmt = select(Project).where(
            Project.organisation_id == organisation_id,
            Project.id == project_id,
        )
        if not include_deleted:
            stmt = stmt.where(Project.deleted_at.is_(None))
        return cast(Project | None, await self._session.scalar(stmt))

    async def list_for_organisation(
        self,
        *,
        organisation_id: UUID,
        limit: int,
        offset: int = 0,
        status: ProjectStatus | None = None,
        name_search: str | None = None,
        include_deleted: bool = False,
    ) -> list[Project]:
        """List projects scoped to one organisation tenant."""

        stmt = select(Project).where(Project.organisation_id == organisation_id)
        if status is not None:
            stmt = stmt.where(Project.status == status)
        if name_search:
            stmt = stmt.where(Project.name.ilike(f"%{name_search}%"))
        if not include_deleted:
            stmt = stmt.where(Project.deleted_at.is_(None))
        stmt = (
            stmt.order_by(Project.created_at.desc(), Project.id.desc()).limit(limit).offset(offset)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def count_for_organisation(
        self,
        *,
        organisation_id: UUID,
        status: ProjectStatus | None = None,
        name_search: str | None = None,
        include_deleted: bool = False,
    ) -> int:
        """Count projects scoped to one organisation tenant."""

        stmt = (
            select(func.count())
            .select_from(Project)
            .where(Project.organisation_id == organisation_id)
        )
        if status is not None:
            stmt = stmt.where(Project.status == status)
        if name_search:
            stmt = stmt.where(Project.name.ilike(f"%{name_search}%"))
        if not include_deleted:
            stmt = stmt.where(Project.deleted_at.is_(None))
        count = await self._session.scalar(stmt)
        return int(count or 0)

    async def update(
        self,
        project: Project,
        *,
        name: str | None = None,
        description: str | None | _UnsetValue = _UNSET,
        status: ProjectStatus | None = None,
        updated_by_user_id: UUID | None = None,
    ) -> Project:
        """Update mutable project fields."""

        if name is not None:
            project.name = name
        if not isinstance(description, _UnsetValue):
            project.description = description
        if status is not None:
            project.status = status
        if updated_by_user_id is not None:
            project.updated_by_user_id = updated_by_user_id
        await self._session.flush()
        return project

    async def delete(
        self,
        project: Project,
        *,
        deleted_at: datetime | None = None,
        updated_by_user_id: UUID | None = None,
    ) -> Project:
        """Soft-delete a project by setting ``deleted_at``."""

        project.deleted_at = deleted_at or datetime.now(UTC)
        if updated_by_user_id is not None:
            project.updated_by_user_id = updated_by_user_id
        await self._session.flush()
        return project
