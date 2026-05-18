"""Organisation-scoped API key management endpoint routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from multi_tenant_saas_api.dependencies import (
    get_api_key_api_service,
    get_current_principal,
    get_idempotency_service,
)
from multi_tenant_saas_api.routes._idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    idempotency_conflict_response,
    idempotency_replay_response,
)
from multi_tenant_saas_api.schemas.api_keys import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListResponse,
    APIKeyResponse,
    APIKeyRevokeResponse,
)
from multi_tenant_saas_api.schemas.common import PaginationMeta
from multi_tenant_saas_api.services import (
    CurrentPrincipal,
    IdempotencyConflictError,
    IdempotencyService,
    OrganisationNotFoundError,
    PermissionDeniedError,
    TenantAccessDeniedError,
)
from multi_tenant_saas_api.services.api_keys import (
    APIKeyAPIService,
    APIKeyList,
    APIKeyNotFoundError,
    CreatedAPIKey,
    PublicAPIKey,
    RevokedAPIKey,
)
from multi_tenant_saas_api.services.idempotency import api_key_idempotency_replay_body


def create_api_key_router() -> APIRouter:
    """Create routes for organisation API key management workflows."""

    router = APIRouter(prefix="/orgs/{organisation_id}/api-keys", tags=["api keys"])

    @router.post(
        "",
        response_model=APIKeyCreateResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create an organisation API key",
    )
    async def create_api_key(
        organisation_id: UUID,
        payload: APIKeyCreateRequest,
        request: Request,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        api_key_service: Annotated[APIKeyAPIService, Depends(get_api_key_api_service)],
        idempotency_service: Annotated[
            IdempotencyService,
            Depends(get_idempotency_service),
        ],
        idempotency_key: Annotated[
            str | None,
            Header(alias=IDEMPOTENCY_KEY_HEADER, min_length=1, max_length=255),
        ] = None,
    ) -> APIKeyCreateResponse | JSONResponse:
        """Create an API key for owner/admin members.

        The raw key is returned only by the initial create response. Idempotent
        replays return stored API key metadata without raw key material.
        """

        try:
            if idempotency_key is not None:
                await api_key_service.ensure_can_create_api_key(
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
            created = await api_key_service.create_api_key(
                principal=principal,
                organisation_id=organisation_id,
                name=payload.name,
            )
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        response = _created_api_key_response(created)
        await idempotency_service.store_response(
            context=idempotency.context,
            response_status_code=status.HTTP_201_CREATED,
            response_body=api_key_idempotency_replay_body(response.model_dump(mode="json")),
        )
        return response

    @router.get(
        "",
        response_model=APIKeyListResponse,
        summary="List organisation API keys",
    )
    async def list_api_keys(
        organisation_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        api_key_service: Annotated[APIKeyAPIService, Depends(get_api_key_api_service)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> APIKeyListResponse:
        """Return API key metadata for owner/admin members."""

        try:
            api_keys = await api_key_service.list_api_keys(
                principal=principal,
                organisation_id=organisation_id,
                limit=limit,
                offset=offset,
            )
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _api_key_list_response(api_keys)

    @router.delete(
        "/{api_key_id}",
        response_model=APIKeyRevokeResponse,
        summary="Revoke an organisation API key",
    )
    async def revoke_api_key(
        organisation_id: UUID,
        api_key_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        api_key_service: Annotated[APIKeyAPIService, Depends(get_api_key_api_service)],
    ) -> APIKeyRevokeResponse:
        """Revoke an API key for owner/admin members."""

        try:
            revoked = await api_key_service.revoke_api_key(
                principal=principal,
                organisation_id=organisation_id,
                api_key_id=api_key_id,
            )
        except APIKeyNotFoundError as exc:
            raise _not_found("api key was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _api_key_revoke_response(revoked)

    return router


def _created_api_key_response(created: CreatedAPIKey) -> APIKeyCreateResponse:
    """Convert service-layer created API key data to a response schema."""

    return APIKeyCreateResponse(api_key=_api_key_response(created.api_key), raw_key=created.raw_key)


def _api_key_response(api_key: PublicAPIKey) -> APIKeyResponse:
    """Convert service-layer API key metadata to the API response schema."""

    return APIKeyResponse.model_validate(api_key)


def _api_key_list_response(api_keys: APIKeyList) -> APIKeyListResponse:
    """Convert a service-layer API key page to the API response schema."""

    items = [_api_key_response(api_key) for api_key in api_keys.items]
    return APIKeyListResponse(
        items=items,
        pagination=PaginationMeta(
            limit=api_keys.limit,
            offset=api_keys.offset,
            total=api_keys.total,
            count=len(items),
        ),
    )


def _api_key_revoke_response(revoked: RevokedAPIKey) -> APIKeyRevokeResponse:
    """Convert a service-layer revoke result to the API response schema."""

    return APIKeyRevokeResponse(
        id=revoked.id,
        organisation_id=revoked.organisation_id,
        revoked_at=revoked.revoked_at,
    )


def _not_found(detail: str) -> HTTPException:
    """Build a safe not-found response."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    """Build a safe tenant access denied response."""

    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


__all__ = ["create_api_key_router"]
