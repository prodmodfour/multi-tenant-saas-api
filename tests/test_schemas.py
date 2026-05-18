from datetime import UTC, datetime
from uuid import UUID

from pydantic import SecretStr, ValidationError
from pytest import raises

from multi_tenant_saas_api.domain import (
    APIKeyID,
    AuditAction,
    AuditEventID,
    MembershipID,
    OrganisationID,
    OrganisationRole,
    ProjectID,
    ProjectStatus,
    UserID,
)
from multi_tenant_saas_api.schemas import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyListResponse,
    APIKeyResponse,
    APIKeyRevokeResponse,
    AuditEventListResponse,
    AuditEventResponse,
    CurrentUserMembershipResponse,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    MembershipCreateRequest,
    MembershipListResponse,
    MembershipResponse,
    MembershipUpdateRequest,
    OrganisationCreateRequest,
    OrganisationListResponse,
    OrganisationResponse,
    OrganisationUpdateRequest,
    PaginationMeta,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
    UserSummary,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
USER_ID = UserID(UUID("00000000-0000-4000-8000-000000000001"))
SECOND_USER_ID = UserID(UUID("00000000-0000-4000-8000-000000000002"))
ORGANISATION_ID = OrganisationID(UUID("00000000-0000-4000-8000-000000000010"))
MEMBERSHIP_ID = MembershipID(UUID("00000000-0000-4000-8000-000000000020"))
PROJECT_ID = ProjectID(UUID("00000000-0000-4000-8000-000000000030"))
API_KEY_ID = APIKeyID(UUID("00000000-0000-4000-8000-000000000040"))
AUDIT_EVENT_ID = AuditEventID(UUID("00000000-0000-4000-8000-000000000050"))


def build_user() -> UserResponse:
    return UserResponse(
        id=USER_ID,
        email="owner@example.com",
        display_name="Owner Example",
        is_active=True,
        created_at=NOW,
        updated_at=NOW,
    )


def build_organisation() -> OrganisationResponse:
    return OrganisationResponse(
        id=ORGANISATION_ID,
        name="Acme Demo",
        slug="acme-demo",
        created_at=NOW,
        updated_at=NOW,
    )


def build_pagination() -> PaginationMeta:
    return PaginationMeta(limit=10, offset=0, total=1, count=1)


def test_register_request_validates_email_and_masks_password_repr() -> None:
    raw_password = "local-demo-password-123"

    request = RegisterRequest.model_validate(
        {
            "email": "owner@example.com",
            "password": raw_password,
            "display_name": "Owner Example",
        }
    )

    assert isinstance(request.password, SecretStr)
    assert request.password.get_secret_value() == raw_password
    assert raw_password not in repr(request)


def test_register_request_rejects_invalid_email_and_short_password() -> None:
    with raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "not-an-email",
                "password": "local-demo-password-123",
                "display_name": "Owner Example",
            }
        )

    with raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "owner@example.com",
                "password": "short",
                "display_name": "Owner Example",
            }
        )


def test_login_schemas_validate_without_exposing_password_hashes() -> None:
    request = LoginRequest.model_validate(
        {"email": "owner@example.com", "password": "local-demo-password-123"}
    )
    response = LoginResponse(access_token="demo-access-token", expires_in_seconds=900)

    assert request.password.get_secret_value() == "local-demo-password-123"
    assert "password_hash" not in UserResponse.model_fields
    assert response.token_type == "bearer"


def test_current_user_and_registration_responses_validate_memberships() -> None:
    user = build_user()
    membership = CurrentUserMembershipResponse(
        membership_id=MEMBERSHIP_ID,
        organisation_id=ORGANISATION_ID,
        organisation_name="Acme Demo",
        organisation_slug="acme-demo",
        role=OrganisationRole.OWNER,
    )

    register_response = RegisterResponse(user=user)
    current_user_response = CurrentUserResponse(user=user, memberships=[membership])

    assert register_response.user.email == "owner@example.com"
    assert current_user_response.memberships[0].role is OrganisationRole.OWNER


def test_organisation_schemas_validate_slug_and_patch_payloads() -> None:
    create_request = OrganisationCreateRequest(name="Acme Demo", slug="acme-demo")
    update_request = OrganisationUpdateRequest(name="Acme Demo Updated")
    list_response = OrganisationListResponse(
        items=[build_organisation()], pagination=build_pagination()
    )

    assert create_request.slug == "acme-demo"
    assert update_request.name == "Acme Demo Updated"
    assert list_response.pagination.total == 1

    with raises(ValidationError):
        OrganisationCreateRequest(name="Acme Demo", slug="Acme Demo")

    with raises(ValidationError):
        OrganisationUpdateRequest()


def test_membership_schemas_validate_roles_and_user_summaries() -> None:
    user_summary = UserSummary(
        id=SECOND_USER_ID,
        email="member@example.com",
        display_name="Member Example",
        is_active=True,
    )
    membership = MembershipResponse(
        id=MEMBERSHIP_ID,
        organisation_id=ORGANISATION_ID,
        user=user_summary,
        role=OrganisationRole.MEMBER,
        created_at=NOW,
        updated_at=NOW,
    )
    create_request = MembershipCreateRequest(user_id=SECOND_USER_ID)
    update_request = MembershipUpdateRequest.model_validate({"role": "viewer"})
    list_response = MembershipListResponse(items=[membership], pagination=build_pagination())

    assert create_request.role is OrganisationRole.MEMBER
    assert update_request.role is OrganisationRole.VIEWER
    assert list_response.items[0].user.email == "member@example.com"

    with raises(ValidationError):
        MembershipUpdateRequest.model_validate({"role": "billing_admin"})


def test_project_schemas_validate_status_and_patch_payloads() -> None:
    create_request = ProjectCreateRequest.model_validate(
        {"name": "Billing Portal", "status": "active"}
    )
    update_request = ProjectUpdateRequest(status=ProjectStatus.ARCHIVED)
    project = ProjectResponse(
        id=PROJECT_ID,
        organisation_id=ORGANISATION_ID,
        name="Billing Portal",
        status=ProjectStatus.ACTIVE,
        description="Public-safe demo project",
        created_by_user_id=USER_ID,
        updated_by_user_id=None,
        created_at=NOW,
        updated_at=NOW,
    )
    list_response = ProjectListResponse(items=[project], pagination=build_pagination())

    assert create_request.status is ProjectStatus.ACTIVE
    assert update_request.status is ProjectStatus.ARCHIVED
    assert list_response.items[0].organisation_id == ORGANISATION_ID

    with raises(ValidationError):
        ProjectCreateRequest.model_validate({"name": "Billing Portal", "status": "done"})

    with raises(ValidationError):
        ProjectCreateRequest.model_validate({"name": "", "status": "active"})

    with raises(ValidationError):
        ProjectUpdateRequest()


def test_api_key_schemas_keep_raw_key_out_of_metadata_responses() -> None:
    api_key = APIKeyResponse(
        id=API_KEY_ID,
        organisation_id=ORGANISATION_ID,
        name="Demo automation",
        key_prefix="saas_demo",
        created_by_user_id=USER_ID,
        revoked_at=None,
        last_used_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    create_request = APIKeyCreateRequest(name="Demo automation")
    create_response = APIKeyCreateResponse(api_key=api_key, raw_key="saas_demo_raw_key_once")
    list_response = APIKeyListResponse(items=[api_key], pagination=build_pagination())
    revoke_response = APIKeyRevokeResponse(
        id=API_KEY_ID,
        organisation_id=ORGANISATION_ID,
        revoked_at=NOW,
    )

    assert create_request.name == "Demo automation"
    assert create_response.raw_key == "saas_demo_raw_key_once"
    assert list_response.items[0].key_prefix == "saas_demo"
    assert revoke_response.status == "revoked"
    assert "raw_key" not in APIKeyResponse.model_fields
    assert "key_hash" not in APIKeyResponse.model_fields
    assert "raw_key" in APIKeyCreateResponse.model_fields


def test_audit_event_schema_validates_secret_safe_metadata() -> None:
    audit_event = AuditEventResponse(
        id=AUDIT_EVENT_ID,
        organisation_id=ORGANISATION_ID,
        actor_user_id=USER_ID,
        actor_api_key_id=None,
        action=AuditAction.PROJECT_CREATED,
        target_type="project",
        target_id=PROJECT_ID,
        metadata={"project_name": "Billing Portal"},
        created_at=NOW,
    )
    list_response = AuditEventListResponse(items=[audit_event], pagination=build_pagination())

    assert list_response.items[0].action is AuditAction.PROJECT_CREATED
    assert "password" not in list_response.items[0].metadata


def test_pagination_metadata_rejects_inconsistent_counts() -> None:
    with raises(ValidationError):
        PaginationMeta(limit=10, offset=0, total=1, count=2)

    with raises(ValidationError):
        PaginationMeta(limit=10, offset=0, total=20, count=11)
