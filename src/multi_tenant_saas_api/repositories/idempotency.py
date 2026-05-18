"""Repository for idempotency record persistence operations."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select

from multi_tenant_saas_api.database import IdempotencyRecord
from multi_tenant_saas_api.repositories.base import BaseRepository


class IdempotencyRecordRepository(BaseRepository):
    """Persist and retrieve scoped idempotency response records."""

    async def create(
        self,
        *,
        principal_type: str,
        principal_id: UUID,
        key: str,
        method: str,
        path: str,
        request_hash: str,
        response_status_code: int,
        response_body: Mapping[str, Any],
        organisation_id: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> IdempotencyRecord:
        """Create an idempotency record scoped to a principal and request."""

        record = IdempotencyRecord(
            principal_type=principal_type,
            principal_id=principal_id,
            organisation_id=organisation_id,
            key=key,
            method=method,
            path=path,
            request_hash=request_hash,
            response_status_code=response_status_code,
            response_body=dict(response_body),
            expires_at=expires_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self,
        *,
        principal_type: str,
        principal_id: UUID,
        key: str,
        method: str,
        path: str,
        organisation_id: UUID | None = None,
    ) -> IdempotencyRecord | None:
        """Return a request-scoped idempotency record, if present."""

        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.principal_type == principal_type,
            IdempotencyRecord.principal_id == principal_id,
            IdempotencyRecord.key == key,
            IdempotencyRecord.method == method,
            IdempotencyRecord.path == path,
        )
        if organisation_id is None:
            stmt = stmt.where(IdempotencyRecord.organisation_id.is_(None))
        else:
            stmt = stmt.where(IdempotencyRecord.organisation_id == organisation_id)
        return cast(IdempotencyRecord | None, await self._session.scalar(stmt))
