"""Pydantic API schemas."""

from multi_tenant_saas_api.schemas.api_keys import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListResponse,
    APIKeyResponse,
    APIKeyRevokeResponse,
)
from multi_tenant_saas_api.schemas.audit import AuditEventListResponse, AuditEventResponse
from multi_tenant_saas_api.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
)
from multi_tenant_saas_api.schemas.common import APIModel, PaginationMeta
from multi_tenant_saas_api.schemas.memberships import (
    CurrentUserMembershipResponse,
    MembershipCreateRequest,
    MembershipListResponse,
    MembershipResponse,
    MembershipUpdateRequest,
)
from multi_tenant_saas_api.schemas.organisations import (
    OrganisationCreateRequest,
    OrganisationListResponse,
    OrganisationResponse,
    OrganisationUpdateRequest,
)
from multi_tenant_saas_api.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from multi_tenant_saas_api.schemas.system import HealthResponse
from multi_tenant_saas_api.schemas.users import UserResponse, UserSummary

__all__ = [
    "APIKeyCreateRequest",
    "APIKeyCreateResponse",
    "APIKeyListResponse",
    "APIKeyResponse",
    "APIKeyRevokeResponse",
    "APIModel",
    "AuditEventListResponse",
    "AuditEventResponse",
    "CurrentUserMembershipResponse",
    "CurrentUserResponse",
    "HealthResponse",
    "LoginRequest",
    "LoginResponse",
    "MembershipCreateRequest",
    "MembershipListResponse",
    "MembershipResponse",
    "MembershipUpdateRequest",
    "OrganisationCreateRequest",
    "OrganisationListResponse",
    "OrganisationResponse",
    "OrganisationUpdateRequest",
    "PaginationMeta",
    "ProjectCreateRequest",
    "ProjectListResponse",
    "ProjectResponse",
    "ProjectUpdateRequest",
    "RegisterRequest",
    "RegisterResponse",
    "UserResponse",
    "UserSummary",
]
