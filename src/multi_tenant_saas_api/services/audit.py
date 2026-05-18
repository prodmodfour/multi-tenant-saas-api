"""Append-only audit event workflows.

The audit service centralises secret-safe audit event creation and authorised
organisation-scoped audit reads. Business services call ``record_event`` inside
their existing unit of work; the service deliberately exposes no update or
delete workflow so audit logs remain append-only at the API/service layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.database import AuditEvent
from multi_tenant_saas_api.domain import (
    APIKeyID,
    AuditAction,
    AuditEventID,
    OrganisationID,
    Permission,
    UserID,
)
from multi_tenant_saas_api.repositories import AuditEventRepository
from multi_tenant_saas_api.services.rbac import CurrentPrincipal, RBACService

_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "authorization",
        "bearer_token",
        "key_hash",
        "password",
        "password_hash",
        "raw_key",
        "raw_password",
        "refresh_token",
        "secret",
        "token",
        "access_token",
    }
)


class AuditServiceError(ValueError):
    """Base class for safe audit service workflow errors."""


class AuditMetadataRejectedError(AuditServiceError):
    """Raised when audit metadata contains an obvious secret-bearing field."""


class AuditReadServiceConfigurationError(AuditServiceError):
    """Raised if audit reads are attempted without RBAC wiring."""


@dataclass(frozen=True, slots=True)
class PublicAuditEvent:
    """Audit event data safe to return from public API workflows."""

    id: AuditEventID
    organisation_id: OrganisationID | None
    actor_user_id: UserID | None
    actor_api_key_id: APIKeyID | None
    action: AuditAction
    target_type: str
    target_id: UUID | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEventPage:
    """Paginated audit event list for one organisation tenant."""

    items: list[PublicAuditEvent]
    limit: int
    offset: int
    total: int


class AuditService:
    """Append-only audit event service.

    Creation validates metadata and writes through the repository without
    committing so the caller's business workflow stays atomic. Reads require an
    RBAC service and the ``read_audit_events`` permission.
    """

    __slots__ = ("_audit_events", "_rbac")

    def __init__(
        self,
        *,
        session: AsyncSession,
        rbac_service: RBACService | None = None,
        audit_event_repository: AuditEventRepository | None = None,
    ) -> None:
        """Initialise audit workflows with repository and optional RBAC collaborators."""

        self._audit_events = audit_event_repository or AuditEventRepository(session)
        self._rbac = rbac_service

    async def record_event(
        self,
        *,
        action: AuditAction,
        target_type: str,
        organisation_id: UUID | OrganisationID | None = None,
        actor_user_id: UUID | UserID | None = None,
        actor_api_key_id: UUID | APIKeyID | None = None,
        target_id: UUID | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PublicAuditEvent:
        """Record one append-only audit event with secret-safe metadata.

        This method intentionally does not commit. The surrounding business
        service owns transaction boundaries so domain writes and audit writes are
        committed or rolled back together.
        """

        metadata_dict = dict(metadata or {})
        _reject_secret_metadata(metadata_dict)
        audit_event = await self._audit_events.create(
            action=action,
            organisation_id=_uuid_or_none(organisation_id),
            actor_user_id=_uuid_or_none(actor_user_id),
            actor_api_key_id=_uuid_or_none(actor_api_key_id),
            target_type=target_type,
            target_id=target_id,
            event_metadata=metadata_dict,
        )
        return _public_audit_event_from_model(audit_event)

    async def list_organisation_events(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        limit: int,
        offset: int,
    ) -> AuditEventPage:
        """List audit events after tenant membership and audit-read permission checks."""

        if self._rbac is None:
            raise AuditReadServiceConfigurationError("audit reads require an RBAC service")

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.READ_AUDIT_EVENTS,
        )
        audit_events = await self._audit_events.list_for_organisation(
            organisation_id=organisation_uuid,
            limit=limit,
            offset=offset,
        )
        total = await self._audit_events.count_for_organisation(organisation_uuid)
        return AuditEventPage(
            items=[_public_audit_event_from_model(audit_event) for audit_event in audit_events],
            limit=limit,
            offset=offset,
            total=total,
        )


def _reject_secret_metadata(metadata: Mapping[str, Any]) -> None:
    """Reject metadata that contains obvious secret-bearing key names."""

    if _contains_forbidden_metadata_key(metadata):
        raise AuditMetadataRejectedError("audit metadata must not include secret fields")


def _contains_forbidden_metadata_key(value: object) -> bool:
    """Return whether a nested metadata value contains a forbidden key."""

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if isinstance(key, str) and _normalise_metadata_key(key) in _FORBIDDEN_METADATA_KEYS:
                return True
            if _contains_forbidden_metadata_key(nested_value):
                return True
        return False
    if isinstance(value, list | tuple):
        return any(_contains_forbidden_metadata_key(item) for item in value)
    return False


def _normalise_metadata_key(key: str) -> str:
    """Normalise metadata key names before comparing them with the deny list."""

    return key.strip().lower().replace("-", "_").replace(" ", "_")


def _public_audit_event_from_model(audit_event: AuditEvent) -> PublicAuditEvent:
    """Convert a repository audit event model to a public DTO."""

    return PublicAuditEvent(
        id=AuditEventID(audit_event.id),
        organisation_id=OrganisationID(audit_event.organisation_id)
        if audit_event.organisation_id is not None
        else None,
        actor_user_id=UserID(audit_event.actor_user_id)
        if audit_event.actor_user_id is not None
        else None,
        actor_api_key_id=APIKeyID(audit_event.actor_api_key_id)
        if audit_event.actor_api_key_id is not None
        else None,
        action=audit_event.action,
        target_type=audit_event.target_type,
        target_id=audit_event.target_id,
        metadata=dict(audit_event.event_metadata),
        created_at=audit_event.created_at,
    )


def _uuid_or_none(value: UUID | OrganisationID | UserID | APIKeyID | None) -> UUID | None:
    """Return a runtime UUID for typed identifiers while preserving ``None``."""

    if value is None:
        return None
    return UUID(str(value))


def _uuid_from_organisation_id(organisation_id: UUID | OrganisationID) -> UUID:
    """Return the runtime UUID value held by an organisation identifier."""

    return UUID(str(organisation_id))


__all__ = [
    "AuditEventPage",
    "AuditMetadataRejectedError",
    "AuditReadServiceConfigurationError",
    "AuditService",
    "AuditServiceError",
    "PublicAuditEvent",
]
