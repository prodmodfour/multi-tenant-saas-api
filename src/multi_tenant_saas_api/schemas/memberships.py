"""Schemas for organisation membership APIs."""

from datetime import datetime

from pydantic import Field

from multi_tenant_saas_api.domain import MembershipID, OrganisationID, OrganisationRole, UserID
from multi_tenant_saas_api.schemas.common import APIModel, PaginationMeta
from multi_tenant_saas_api.schemas.users import UserSummary


class MembershipCreateRequest(APIModel):
    """Request to add an existing user to an organisation."""

    user_id: UserID
    role: OrganisationRole = Field(default=OrganisationRole.MEMBER)


class MembershipUpdateRequest(APIModel):
    """Request to change a member's role."""

    role: OrganisationRole


class MembershipResponse(APIModel):
    """Organisation membership response without secret user data."""

    id: MembershipID
    organisation_id: OrganisationID
    user: UserSummary
    role: OrganisationRole
    created_at: datetime
    updated_at: datetime


class MembershipListResponse(APIModel):
    """Paginated membership list response."""

    items: list[MembershipResponse]
    pagination: PaginationMeta


class CurrentUserMembershipResponse(APIModel):
    """Membership summary embedded in the current-user response."""

    membership_id: MembershipID
    organisation_id: OrganisationID
    organisation_name: str = Field(min_length=1, max_length=120)
    organisation_slug: str = Field(min_length=3, max_length=80)
    role: OrganisationRole
