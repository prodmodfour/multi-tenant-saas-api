"""Repository for append-only audit event persistence operations."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from multi_tenant_saas_api.database import AuditEvent
from multi_tenant_saas_api.domain import AuditAction
from multi_tenant_saas_api.repositories.base import BaseRepository


class AuditEventRepository(BaseRepository):
    """Persist and retrieve audit events."""

    async def create(
        self,
        *,
        action: AuditAction,
        target_type: str,
        organisation_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        actor_api_key_id: UUID | None = None,
        target_id: UUID | None = None,
        event_metadata: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        """Create an audit event.

        Callers are responsible for passing secret-safe metadata; this repository
        stores only the structured metadata it is given.
        """

        audit_event = AuditEvent(
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            actor_api_key_id=actor_api_key_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            event_metadata=dict(event_metadata or {}),
        )
        self._session.add(audit_event)
        await self._session.flush()
        return audit_event

    async def list_for_organisation(
        self,
        *,
        organisation_id: UUID,
        limit: int,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """List audit events scoped to one organisation tenant."""

        stmt = (
            select(AuditEvent)
            .where(AuditEvent.organisation_id == organisation_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def count_for_organisation(self, organisation_id: UUID) -> int:
        """Count audit events scoped to one organisation tenant."""

        stmt = (
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.organisation_id == organisation_id)
        )
        count = await self._session.scalar(stmt)
        return int(count or 0)
