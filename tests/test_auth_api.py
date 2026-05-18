from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ClauseElement

from multi_tenant_saas_api.app import create_app
from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.database import AuditEvent, Organisation, OrganisationMembership, User
from multi_tenant_saas_api.dependencies import get_session
from multi_tenant_saas_api.domain import AuditAction, OrganisationRole, UserID
from multi_tenant_saas_api.services import AccessTokenService, PasswordHashingService

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-auth-api"
JWT_ISSUER = "multi-tenant-saas-api-auth-api-test"
RAW_PASSWORD = "local-demo-password-123"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeScalarResult[ScalarT]:
    def __init__(self, values: Sequence[ScalarT]) -> None:
        self._values = list(values)

    def all(self) -> Sequence[ScalarT]:
        return self._values


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = 0
        self.flushed = 0
        self.rolled_back = 0
        self.scalar_results: list[object | None] = []
        self.scalars_results: list[FakeScalarResult[object]] = []
        self.scalar_statements: list[ClauseElement] = []
        self.scalars_statements: list[ClauseElement] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def flush(self) -> None:
        self.flushed += 1
        for instance in self.added:
            attributes = vars(instance)
            if "id" not in attributes or attributes["id"] is None:
                attributes["id"] = uuid4()
            if "created_at" not in attributes or attributes["created_at"] is None:
                attributes["created_at"] = NOW
            if not isinstance(instance, AuditEvent) and (
                "updated_at" not in attributes or attributes["updated_at"] is None
            ):
                attributes["updated_at"] = NOW

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1

    async def scalar(self, statement: ClauseElement) -> object | None:
        self.scalar_statements.append(statement)
        if not self.scalar_results:
            return None
        return self.scalar_results.pop(0)

    async def scalars(self, statement: ClauseElement) -> FakeScalarResult[object]:
        self.scalars_statements.append(statement)
        if not self.scalars_results:
            return FakeScalarResult(())
        return self.scalars_results.pop(0)


def as_session(fake: FakeSession) -> AsyncSession:
    return cast(AsyncSession, fake)


def make_settings() -> Settings:
    return Settings(
        environment="test",
        log_level="WARNING",
        docs_enabled=False,
        jwt_secret=SecretStr(JWT_SECRET),
        jwt_issuer=JWT_ISSUER,
        access_token_ttl_seconds=900,
        password_min_length=12,
    )


def build_client(fake_session: FakeSession) -> TestClient:
    app = create_app(make_settings())

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield as_session(fake_session)

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def make_user(
    *,
    user_id: UUID | None = None,
    email: str = "owner@example.com",
    password_hash: str | None = None,
    is_active: bool = True,
) -> User:
    return User(
        id=user_id or uuid4(),
        email=email,
        display_name="Owner Example",
        password_hash=password_hash or PasswordHashingService().hash_password(RAW_PASSWORD),
        is_active=is_active,
        created_at=NOW,
        updated_at=NOW,
    )


def make_organisation(*, organisation_id: UUID | None = None) -> Organisation:
    return Organisation(
        id=organisation_id or uuid4(),
        name="Acme Demo",
        slug="acme-demo",
        created_at=NOW,
        updated_at=NOW,
    )


def test_register_creates_user_with_hashed_password_and_audit_event() -> None:
    fake = FakeSession()
    fake.scalar_results.append(None)
    client = build_client(fake)

    response = client.post(
        "/auth/register",
        json={
            "email": "Owner@Example.com",
            "password": RAW_PASSWORD,
            "display_name": "Owner Example",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "owner@example.com"
    assert body["user"]["display_name"] == "Owner Example"
    assert body["user"]["is_active"] is True
    assert "password" not in response.text.lower()
    assert RAW_PASSWORD not in response.text

    created_user = next(instance for instance in fake.added if isinstance(instance, User))
    assert created_user.email == "owner@example.com"
    assert created_user.password_hash != RAW_PASSWORD
    assert RAW_PASSWORD not in created_user.password_hash
    assert UUID(body["user"]["id"]) == created_user.id

    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert audit_event.action is AuditAction.USER_REGISTERED
    assert audit_event.actor_user_id == created_user.id
    assert audit_event.target_type == "user"
    assert audit_event.target_id == created_user.id
    assert audit_event.event_metadata == {}
    assert audit_event.organisation_id is None
    assert fake.committed == 1
    assert fake.rolled_back == 0


def test_register_rejects_duplicate_email_without_leaking_password() -> None:
    fake = FakeSession()
    fake.scalar_results.append(make_user(email="owner@example.com"))
    client = build_client(fake)

    response = client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "password": RAW_PASSWORD,
            "display_name": "Owner Example",
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "email is already registered"}
    assert RAW_PASSWORD not in response.text
    assert fake.added == []
    assert fake.committed == 0


def test_login_returns_bearer_token_and_records_safe_audit_event() -> None:
    user_id = uuid4()
    user = make_user(user_id=user_id)
    fake = FakeSession()
    fake.scalar_results.append(user)
    client = build_client(fake)

    response = client.post(
        "/auth/login",
        json={"email": "OWNER@example.com", "password": RAW_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in_seconds"] == 900
    assert body["access_token"]
    assert RAW_PASSWORD not in response.text

    token_service = AccessTokenService.from_settings(make_settings())
    principal = token_service.validate_access_token(body["access_token"])
    assert principal.user_id == UserID(user_id)

    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert audit_event.action is AuditAction.USER_LOGGED_IN
    assert audit_event.actor_user_id == user_id
    assert audit_event.target_type == "user"
    assert audit_event.target_id == user_id
    assert audit_event.event_metadata == {}
    assert fake.committed == 1


def test_login_uses_same_safe_error_for_unknown_email_and_wrong_password() -> None:
    unknown_email_fake = FakeSession()
    unknown_email_fake.scalar_results.append(None)
    unknown_email_client = build_client(unknown_email_fake)

    unknown_email_response = unknown_email_client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": RAW_PASSWORD},
    )

    wrong_password_fake = FakeSession()
    wrong_password_fake.scalar_results.append(make_user())
    wrong_password_client = build_client(wrong_password_fake)

    wrong_password_response = wrong_password_client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "wrong-local-demo-password"},
    )

    assert unknown_email_response.status_code == 401
    assert wrong_password_response.status_code == 401
    assert unknown_email_response.json() == wrong_password_response.json()
    assert unknown_email_response.json() == {"detail": "invalid email or password"}
    assert RAW_PASSWORD not in unknown_email_response.text
    assert "wrong-local-demo-password" not in wrong_password_response.text
    assert unknown_email_fake.added == []
    assert wrong_password_fake.added == []


def test_get_me_returns_current_user_and_organisation_memberships() -> None:
    user_id = uuid4()
    organisation_id = uuid4()
    membership_id = uuid4()
    user = make_user(user_id=user_id)
    organisation = make_organisation(organisation_id=organisation_id)
    membership = OrganisationMembership(
        id=membership_id,
        organisation_id=organisation_id,
        user_id=user_id,
        role=OrganisationRole.OWNER,
        created_at=NOW,
        updated_at=NOW,
    )
    token = AccessTokenService.from_settings(make_settings()).create_access_token(UserID(user_id))
    fake = FakeSession()
    fake.scalar_results.extend([user, organisation])
    fake.scalars_results.append(FakeScalarResult([membership]))
    client = build_client(fake)

    response = client.get("/me", headers={"Authorization": f"Bearer {token.token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user_id)
    assert body["user"]["email"] == "owner@example.com"
    assert body["memberships"] == [
        {
            "membership_id": str(membership_id),
            "organisation_id": str(organisation_id),
            "organisation_name": "Acme Demo",
            "organisation_slug": "acme-demo",
            "role": "owner",
        }
    ]
    assert "password" not in response.text.lower()
    assert fake.committed == 0


def test_get_me_requires_valid_bearer_token() -> None:
    missing_token_fake = FakeSession()
    missing_token_client = build_client(missing_token_fake)

    missing_token_response = missing_token_client.get("/me")

    invalid_token_fake = FakeSession()
    invalid_token_client = build_client(invalid_token_fake)

    invalid_token_response = invalid_token_client.get(
        "/me",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert missing_token_response.status_code == 401
    assert missing_token_response.headers["WWW-Authenticate"] == "Bearer"
    assert missing_token_response.json() == {"detail": "authentication required"}
    assert invalid_token_response.status_code == 401
    assert invalid_token_response.headers["WWW-Authenticate"] == "Bearer"
    assert invalid_token_response.json() == {"detail": "invalid or expired access token"}
    assert missing_token_fake.scalar_statements == []
    assert invalid_token_fake.scalar_statements == []
