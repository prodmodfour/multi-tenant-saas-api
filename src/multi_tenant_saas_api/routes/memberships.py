"""Organisation membership management endpoint routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from multi_tenant_saas_api.dependencies import get_current_principal, get_membership_api_service
from multi_tenant_saas_api.schemas.common import PaginationMeta
from multi_tenant_saas_api.schemas.memberships import (
    MembershipCreateRequest,
    MembershipListResponse,
    MembershipResponse,
    MembershipUpdateRequest,
)
from multi_tenant_saas_api.services import (
    CurrentPrincipal,
    LastOwnerProtectionError,
    OrganisationNotFoundError,
    PermissionDeniedError,
    TenantAccessDeniedError,
)
from multi_tenant_saas_api.services.memberships import (
    MembershipAlreadyExistsError,
    MembershipAPIService,
    MembershipList,
    MembershipNotFoundError,
    PublicMembership,
    TargetUserNotFoundError,
)


def create_membership_router() -> APIRouter:
    """Create routes for organisation membership management workflows."""

    router = APIRouter(prefix="/orgs/{organisation_id}/members", tags=["memberships"])

    @router.get(
        "",
        response_model=MembershipListResponse,
        summary="List organisation members",
    )
    async def list_members(
        organisation_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        membership_service: Annotated[
            MembershipAPIService,
            Depends(get_membership_api_service),
        ],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> MembershipListResponse:
        """Return organisation members for owner/admin roles."""

        try:
            memberships = await membership_service.list_members(
                principal=principal,
                organisation_id=organisation_id,
                limit=limit,
                offset=offset,
            )
        except TargetUserNotFoundError as exc:
            raise _not_found("user was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _membership_list_response(memberships)

    @router.post(
        "",
        response_model=MembershipResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Add an organisation member",
    )
    async def add_member(
        organisation_id: UUID,
        payload: MembershipCreateRequest,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        membership_service: Annotated[
            MembershipAPIService,
            Depends(get_membership_api_service),
        ],
    ) -> MembershipResponse:
        """Add an existing user to an organisation for owner/admin roles."""

        try:
            membership = await membership_service.add_member(
                principal=principal,
                organisation_id=organisation_id,
                target_user_id=payload.user_id,
                role=payload.role,
            )
        except MembershipAlreadyExistsError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="user is already a member of this organisation",
            ) from exc
        except TargetUserNotFoundError as exc:
            raise _not_found("user was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _membership_response(membership)

    @router.patch(
        "/{user_id}",
        response_model=MembershipResponse,
        summary="Update an organisation member role",
    )
    async def update_member_role(
        organisation_id: UUID,
        user_id: UUID,
        payload: MembershipUpdateRequest,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        membership_service: Annotated[
            MembershipAPIService,
            Depends(get_membership_api_service),
        ],
    ) -> MembershipResponse:
        """Update a member role while preserving the last-owner invariant."""

        try:
            membership = await membership_service.update_member_role(
                principal=principal,
                organisation_id=organisation_id,
                target_user_id=user_id,
                role=payload.role,
            )
        except LastOwnerProtectionError as exc:
            raise _conflict("organisation must always have at least one owner") from exc
        except MembershipNotFoundError as exc:
            raise _not_found("membership was not found") from exc
        except TargetUserNotFoundError as exc:
            raise _not_found("user was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return _membership_response(membership)

    @router.delete(
        "/{user_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Remove an organisation member",
    )
    async def remove_member(
        organisation_id: UUID,
        user_id: UUID,
        principal: Annotated[CurrentPrincipal, Depends(get_current_principal)],
        membership_service: Annotated[
            MembershipAPIService,
            Depends(get_membership_api_service),
        ],
    ) -> Response:
        """Remove a member while preserving the last-owner invariant."""

        try:
            await membership_service.remove_member(
                principal=principal,
                organisation_id=organisation_id,
                target_user_id=user_id,
            )
        except LastOwnerProtectionError as exc:
            raise _conflict("organisation must always have at least one owner") from exc
        except MembershipNotFoundError as exc:
            raise _not_found("membership was not found") from exc
        except OrganisationNotFoundError as exc:
            raise _not_found("organisation was not found") from exc
        except PermissionDeniedError as exc:
            raise _forbidden("insufficient permissions for this organisation") from exc
        except TenantAccessDeniedError as exc:
            raise _forbidden("organisation access denied") from exc

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _membership_response(membership: PublicMembership) -> MembershipResponse:
    """Convert service-layer membership data to the API response schema."""

    return MembershipResponse.model_validate(membership)


def _membership_list_response(memberships: MembershipList) -> MembershipListResponse:
    """Convert a service-layer membership page to the API response schema."""

    items = [_membership_response(membership) for membership in memberships.items]
    return MembershipListResponse(
        items=items,
        pagination=PaginationMeta(
            limit=memberships.limit,
            offset=memberships.offset,
            total=memberships.total,
            count=len(items),
        ),
    )


def _not_found(detail: str) -> HTTPException:
    """Build a safe not-found response."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    """Build a safe tenant access denied response."""

    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _conflict(detail: str) -> HTTPException:
    """Build a safe conflict response."""

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


__all__ = ["create_membership_router"]
