"""Idempotency support for unsafe API creation workflows.

The service stores response snapshots for requests that provide an
``Idempotency-Key`` header. Records are scoped to the authenticated principal,
HTTP method, path, request body hash, and organisation where applicable so keys
cannot replay behaviour across users, API keys, tenants, methods, or endpoints.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.domain import APIKeyID, OrganisationID, UserID
from multi_tenant_saas_api.repositories import IdempotencyRecordRepository
from multi_tenant_saas_api.services.api_keys import ProjectPrincipal
from multi_tenant_saas_api.services.auth import PrincipalType
from multi_tenant_saas_api.services.rbac import CurrentPrincipal

_HASH_ENCODING = "utf-8"
_IDEMPOTENCY_REPLAY_NOTE = (
    "raw API key material is returned only by the initial create response and is not replayed"
)
_SECRET_SNAPSHOT_FIELD_NAMES = frozenset(
    {
        "access_token",
        "authorization",
        "bearer_token",
        "key_hash",
        "password",
        "password_hash",
        "raw_api_key",
        "raw_key",
        "token",
    }
)


class IdempotencyServiceError(ValueError):
    """Base class for safe idempotency workflow errors."""


class IdempotencyConflictError(IdempotencyServiceError):
    """Raised when an idempotency key is reused with a different body hash."""


class IdempotencySecretSnapshotRejectedError(IdempotencyServiceError):
    """Raised when a response snapshot contains obvious secret-bearing fields."""


@dataclass(frozen=True, slots=True)
class IdempotencyContext:
    """Resolved idempotency scope for one unsafe request."""

    principal_type: PrincipalType
    principal_id: UUID
    organisation_id: UUID | None
    key: str
    method: str
    path: str
    request_hash: str


@dataclass(frozen=True, slots=True)
class IdempotencyReplay:
    """Stored response snapshot for a repeated idempotent request."""

    response_status_code: int
    response_body: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    """Idempotency lookup result for a route workflow."""

    context: IdempotencyContext | None
    replay: IdempotencyReplay | None


class IdempotencyService:
    """Service layer for idempotency key lookups and response snapshots."""

    __slots__ = ("_records", "_session")

    def __init__(
        self,
        *,
        session: AsyncSession,
        idempotency_repository: IdempotencyRecordRepository | None = None,
    ) -> None:
        """Initialise idempotency workflows with repository collaborators."""

        self._session = session
        self._records = idempotency_repository or IdempotencyRecordRepository(session)

    async def start_request(
        self,
        *,
        key: str | None,
        principal: ProjectPrincipal,
        method: str,
        path: str,
        request_body: BaseModel | Mapping[str, Any],
        organisation_id: UUID | OrganisationID | None = None,
    ) -> IdempotencyDecision:
        """Return replay data or a context for storing the eventual response.

        Missing keys are a no-op so routes can call this for all supported
        unsafe endpoints without changing behaviour for ordinary requests.
        """

        if key is None:
            return IdempotencyDecision(context=None, replay=None)

        context = IdempotencyContext(
            principal_type=_principal_type(principal),
            principal_id=_principal_id(principal),
            organisation_id=_uuid_from_organisation_id(organisation_id)
            if organisation_id is not None
            else None,
            key=key,
            method=method.upper(),
            path=path,
            request_hash=request_hash(request_body),
        )
        existing_record = await self._records.get(
            principal_type=context.principal_type.value,
            principal_id=context.principal_id,
            organisation_id=context.organisation_id,
            key=context.key,
            method=context.method,
            path=context.path,
        )
        if existing_record is None:
            return IdempotencyDecision(context=context, replay=None)

        if existing_record.request_hash != context.request_hash:
            raise IdempotencyConflictError(
                "idempotency key was already used with a different request body"
            )

        return IdempotencyDecision(
            context=context,
            replay=IdempotencyReplay(
                response_status_code=existing_record.response_status_code,
                response_body=existing_record.response_body,
            ),
        )

    async def store_response(
        self,
        *,
        context: IdempotencyContext | None,
        response_status_code: int,
        response_body: Mapping[str, Any],
    ) -> None:
        """Persist a response snapshot for future idempotent replay.

        Snapshots reject obvious secret-bearing fields. Callers that create API
        keys must pass a sanitized body that omits raw key material.
        """

        if context is None:
            return

        secret_field = _find_secret_snapshot_field(response_body)
        if secret_field is not None:
            raise IdempotencySecretSnapshotRejectedError(
                f"idempotency response snapshot contains secret field: {secret_field}"
            )

        try:
            await self._records.create(
                principal_type=context.principal_type.value,
                principal_id=context.principal_id,
                organisation_id=context.organisation_id,
                key=context.key,
                method=context.method,
                path=context.path,
                request_hash=context.request_hash,
                response_status_code=response_status_code,
                response_body=response_body,
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise


def request_hash(request_body: BaseModel | Mapping[str, Any]) -> str:
    """Return a deterministic SHA-256 hash for a validated request body."""

    if isinstance(request_body, BaseModel):
        body = request_body.model_dump(mode="json", by_alias=True)
    else:
        body = dict(request_body)
    encoded_body = json.dumps(
        body,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode(_HASH_ENCODING)
    return hashlib.sha256(encoded_body).hexdigest()


def api_key_idempotency_replay_body(response_body: Mapping[str, Any]) -> dict[str, Any]:
    """Return an API key creation snapshot that omits one-time raw key material."""

    sanitized = {key: value for key, value in response_body.items() if key != "raw_key"}
    sanitized["idempotency_replay"] = {
        "secret_available": False,
        "reason": _IDEMPOTENCY_REPLAY_NOTE,
    }
    return sanitized


def _principal_type(principal: ProjectPrincipal) -> PrincipalType:
    """Return the principal type used for idempotency scoping."""

    return principal.principal_type


def _principal_id(principal: ProjectPrincipal) -> UUID:
    """Return the non-secret principal identifier used for idempotency scoping."""

    if isinstance(principal, CurrentPrincipal):
        return _uuid_from_user_id(principal.user_id)
    return _uuid_from_api_key_id(principal.api_key_id)


def _uuid_from_user_id(user_id: UUID | UserID) -> UUID:
    """Return the runtime UUID value held by a user identifier."""

    return UUID(str(user_id))


def _uuid_from_api_key_id(api_key_id: UUID | APIKeyID) -> UUID:
    """Return the runtime UUID value held by an API key identifier."""

    return UUID(str(api_key_id))


def _uuid_from_organisation_id(organisation_id: UUID | OrganisationID) -> UUID:
    """Return the runtime UUID value held by an organisation identifier."""

    return UUID(str(organisation_id))


def _find_secret_snapshot_field(value: object) -> str | None:
    """Return the first obvious secret-bearing field name in a response body."""

    if isinstance(value, Mapping):
        for raw_key, nested_value in value.items():
            field_name = str(raw_key)
            if _is_secret_snapshot_field(field_name):
                return field_name
            nested_secret = _find_secret_snapshot_field(nested_value)
            if nested_secret is not None:
                return nested_secret
    elif isinstance(value, list):
        for nested_value in value:
            nested_secret = _find_secret_snapshot_field(nested_value)
            if nested_secret is not None:
                return nested_secret
    return None


def _is_secret_snapshot_field(field_name: str) -> bool:
    """Return whether a field name should never be stored in a replay snapshot."""

    normalised = field_name.strip().lower()
    return normalised in _SECRET_SNAPSHOT_FIELD_NAMES or normalised.endswith("_token")


__all__ = [
    "IdempotencyConflictError",
    "IdempotencyContext",
    "IdempotencyDecision",
    "IdempotencyReplay",
    "IdempotencySecretSnapshotRejectedError",
    "IdempotencyService",
    "IdempotencyServiceError",
    "api_key_idempotency_replay_body",
    "request_hash",
]
