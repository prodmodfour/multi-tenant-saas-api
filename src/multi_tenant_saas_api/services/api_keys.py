"""Organisation-scoped API key management and authentication services.

This module owns API key creation, listing, revocation, hashing, and project
endpoint authentication. Raw API key material is generated only for the
one-time create response and is never persisted, logged, or written to audit
metadata.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.database import APIKey
from multi_tenant_saas_api.domain import APIKeyID, AuditAction, OrganisationID, Permission, UserID
from multi_tenant_saas_api.repositories import APIKeyRepository, AuditEventRepository
from multi_tenant_saas_api.services.auth import PrincipalType
from multi_tenant_saas_api.services.rbac import (
    CurrentPrincipal,
    PrincipalResolutionError,
    RBACService,
)

_API_KEY_RAW_PREFIX = "saas_demo_"
_API_KEY_PREFIX_LENGTH = 16
_API_KEY_HASH_ENCODING = "utf-8"


class APIKeyAPIServiceError(ValueError):
    """Base class for safe API key workflow errors."""


class APIKeyNotFoundError(APIKeyAPIServiceError):
    """Raised when a tenant-scoped API key does not exist."""


class APIKeyAuthenticationError(APIKeyAPIServiceError):
    """Raised when bearer credentials cannot resolve to a user or API key."""


@dataclass(frozen=True, slots=True)
class PublicAPIKey:
    """API key metadata safe to return from public API workflows."""

    id: APIKeyID
    organisation_id: OrganisationID
    name: str
    key_prefix: str
    created_by_user_id: UserID | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CreatedAPIKey:
    """Created API key metadata plus the one-time raw key value."""

    api_key: PublicAPIKey
    raw_key: str


@dataclass(frozen=True, slots=True)
class APIKeyList:
    """Paginated API key metadata list for one organisation tenant."""

    items: list[PublicAPIKey]
    limit: int
    offset: int
    total: int


@dataclass(frozen=True, slots=True)
class RevokedAPIKey:
    """Revoked API key result safe to return from the API."""

    id: APIKeyID
    organisation_id: OrganisationID
    revoked_at: datetime


@dataclass(frozen=True, slots=True)
class APIKeyPrincipal:
    """Secret-safe principal resolved from a valid organisation API key."""

    principal_type: PrincipalType
    api_key_id: APIKeyID
    organisation_id: OrganisationID
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None


ProjectPrincipal = CurrentPrincipal | APIKeyPrincipal


class APIKeySecretService:
    """Generate and hash high-entropy API key material.

    API keys are random bearer secrets. The persisted value is a deterministic
    SHA-256 digest so incoming keys can be looked up without storing raw key
    material. Production systems may additionally use a dedicated secret pepper
    from managed secret storage.
    """

    __slots__ = ()

    def generate_raw_key(self) -> str:
        """Return one high-entropy raw API key for a create response."""

        return f"{_API_KEY_RAW_PREFIX}{secrets.token_urlsafe(32)}"

    def key_prefix(self, raw_key: str) -> str:
        """Return the non-secret identification prefix stored for an API key."""

        return raw_key[:_API_KEY_PREFIX_LENGTH]

    def hash_key(self, raw_key: str) -> str:
        """Return a deterministic digest suitable for API key persistence."""

        return hashlib.sha256(raw_key.encode(_API_KEY_HASH_ENCODING)).hexdigest()


class APIKeyAPIService:
    """Service layer for organisation-scoped API key management endpoints."""

    __slots__ = ("_api_keys", "_audit_events", "_key_secrets", "_rbac", "_session")

    def __init__(
        self,
        *,
        session: AsyncSession,
        rbac_service: RBACService,
        api_key_repository: APIKeyRepository | None = None,
        audit_event_repository: AuditEventRepository | None = None,
        key_secret_service: APIKeySecretService | None = None,
    ) -> None:
        """Initialise API key workflows with repository collaborators."""

        self._session = session
        self._rbac = rbac_service
        self._api_keys = api_key_repository or APIKeyRepository(session)
        self._audit_events = audit_event_repository or AuditEventRepository(session)
        self._key_secrets = key_secret_service or APIKeySecretService()

    async def create_api_key(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        name: str,
    ) -> CreatedAPIKey:
        """Create an API key after tenant and manage-key checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.MANAGE_API_KEYS,
        )

        raw_key = self._key_secrets.generate_raw_key()
        key_prefix = self._key_secrets.key_prefix(raw_key)
        key_hash = self._key_secrets.hash_key(raw_key)
        actor_user_id = _uuid_from_user_id(principal.user_id)

        try:
            api_key = await self._api_keys.create(
                organisation_id=organisation_uuid,
                name=name,
                key_prefix=key_prefix,
                key_hash=key_hash,
                created_by_user_id=actor_user_id,
            )
            await self._audit_events.create(
                action=AuditAction.API_KEY_CREATED,
                organisation_id=organisation_uuid,
                actor_user_id=actor_user_id,
                target_type="api_key",
                target_id=api_key.id,
                event_metadata={"api_key_name": api_key.name, "key_prefix": api_key.key_prefix},
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return CreatedAPIKey(api_key=_public_api_key_from_model(api_key), raw_key=raw_key)

    async def list_api_keys(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        limit: int,
        offset: int,
    ) -> APIKeyList:
        """List API key metadata after tenant and manage-key checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.MANAGE_API_KEYS,
        )
        api_keys = await self._api_keys.list_for_organisation(
            organisation_id=organisation_uuid,
            limit=limit,
            offset=offset,
        )
        total = await self._api_keys.count_for_organisation(organisation_id=organisation_uuid)
        return APIKeyList(
            items=[_public_api_key_from_model(api_key) for api_key in api_keys],
            limit=limit,
            offset=offset,
            total=total,
        )

    async def revoke_api_key(
        self,
        *,
        principal: CurrentPrincipal,
        organisation_id: UUID | OrganisationID,
        api_key_id: UUID | APIKeyID,
    ) -> RevokedAPIKey:
        """Revoke one API key after tenant and manage-key checks."""

        organisation_uuid = _uuid_from_organisation_id(organisation_id)
        actor_user_id = _uuid_from_user_id(principal.user_id)
        await self._rbac.get_tenant_context(
            principal=principal,
            organisation_id=organisation_uuid,
            required_permission=Permission.MANAGE_API_KEYS,
        )
        api_key = await self._api_keys.get_by_id(
            organisation_id=organisation_uuid,
            api_key_id=_uuid_from_api_key_id(api_key_id),
        )
        if api_key is None:
            raise APIKeyNotFoundError("api key was not found")

        try:
            if api_key.revoked_at is None:
                api_key = await self._api_keys.revoke(api_key)
                await self._audit_events.create(
                    action=AuditAction.API_KEY_REVOKED,
                    organisation_id=organisation_uuid,
                    actor_user_id=actor_user_id,
                    target_type="api_key",
                    target_id=api_key.id,
                    event_metadata={
                        "api_key_name": api_key.name,
                        "key_prefix": api_key.key_prefix,
                    },
                )
                await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        if api_key.revoked_at is None:
            msg = "api key revoke did not set revoked_at"
            raise RuntimeError(msg)
        return RevokedAPIKey(
            id=APIKeyID(api_key.id),
            organisation_id=OrganisationID(api_key.organisation_id),
            revoked_at=api_key.revoked_at,
        )


class APIKeyAuthenticationService:
    """Resolve bearer credentials for project endpoints.

    Project endpoints accept either an existing user access token or an active
    organisation API key. Other business routes continue to use user access
    tokens only.
    """

    __slots__ = ("_api_keys", "_key_secrets", "_rbac", "_session")

    def __init__(
        self,
        *,
        session: AsyncSession,
        rbac_service: RBACService,
        api_key_repository: APIKeyRepository | None = None,
        key_secret_service: APIKeySecretService | None = None,
    ) -> None:
        """Initialise project principal resolution dependencies."""

        self._session = session
        self._rbac = rbac_service
        self._api_keys = api_key_repository or APIKeyRepository(session)
        self._key_secrets = key_secret_service or APIKeySecretService()

    async def resolve_project_principal(self, *, bearer_token: str) -> ProjectPrincipal:
        """Resolve a user access token or active API key for project endpoints."""

        try:
            return await self._rbac.resolve_current_principal(bearer_token=bearer_token)
        except PrincipalResolutionError:
            pass

        key_hash = self._key_secrets.hash_key(bearer_token)
        api_key = await self._api_keys.get_active_by_hash(key_hash)
        if api_key is None:
            raise APIKeyAuthenticationError("invalid or revoked API key")

        try:
            api_key = await self._api_keys.update_last_used(api_key)
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise

        return _api_key_principal_from_model(api_key)


def _public_api_key_from_model(api_key: APIKey) -> PublicAPIKey:
    """Convert repository API key metadata to a secret-safe DTO."""

    return PublicAPIKey(
        id=APIKeyID(api_key.id),
        organisation_id=OrganisationID(api_key.organisation_id),
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        created_by_user_id=UserID(api_key.created_by_user_id)
        if api_key.created_by_user_id is not None
        else None,
        revoked_at=api_key.revoked_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


def _api_key_principal_from_model(api_key: APIKey) -> APIKeyPrincipal:
    """Build a secret-safe principal from active API key metadata."""

    return APIKeyPrincipal(
        principal_type=PrincipalType.API_KEY,
        api_key_id=APIKeyID(api_key.id),
        organisation_id=OrganisationID(api_key.organisation_id),
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
    )


def _uuid_from_user_id(user_id: UUID | UserID) -> UUID:
    """Return the runtime UUID value held by a typed user identifier."""

    return UUID(str(user_id))


def _uuid_from_organisation_id(organisation_id: UUID | OrganisationID) -> UUID:
    """Return the runtime UUID value held by a typed organisation identifier."""

    return UUID(str(organisation_id))


def _uuid_from_api_key_id(api_key_id: UUID | APIKeyID) -> UUID:
    """Return the runtime UUID value held by a typed API key identifier."""

    return UUID(str(api_key_id))


__all__ = [
    "APIKeyAPIService",
    "APIKeyAPIServiceError",
    "APIKeyAuthenticationError",
    "APIKeyAuthenticationService",
    "APIKeyList",
    "APIKeyNotFoundError",
    "APIKeyPrincipal",
    "APIKeySecretService",
    "CreatedAPIKey",
    "ProjectPrincipal",
    "PublicAPIKey",
    "RevokedAPIKey",
]
