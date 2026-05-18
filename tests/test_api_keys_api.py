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
from multi_tenant_saas_api.database import (
    APIKey,
    AuditEvent,
    Organisation,
    OrganisationMembership,
    Project,
    User,
)
from multi_tenant_saas_api.dependencies import get_session
from multi_tenant_saas_api.domain import AuditAction, OrganisationRole, ProjectStatus, UserID
from multi_tenant_saas_api.services import AccessTokenService
from multi_tenant_saas_api.services.api_keys import APIKeySecretService

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-api-keys"
JWT_ISSUER = "multi-tenant-saas-api-api-key-test"
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
            if isinstance(instance, AuditEvent) and attributes.get("event_metadata") is None:
                attributes["event_metadata"] = {}

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


def compile_sql(statement: ClauseElement) -> str:
    return str(statement.compile())


def make_settings() -> Settings:
    return Settings(
        environment="test",
        log_level="WARNING",
        docs_enabled=False,
        jwt_secret=SecretStr(JWT_SECRET),
        jwt_issuer=JWT_ISSUER,
        access_token_ttl_seconds=900,
    )


def build_client(fake_session: FakeSession) -> TestClient:
    app = create_app(make_settings())

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield as_session(fake_session)

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def bearer_header(user_id: UUID) -> dict[str, str]:
    access_token = AccessTokenService.from_settings(make_settings()).create_access_token(
        UserID(user_id)
    )
    return {"Authorization": f"Bearer {access_token.token}"}


def api_key_header(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


def make_user(*, user_id: UUID | None = None) -> User:
    return User(
        id=user_id or uuid4(),
        email="owner@example.com",
        display_name="Owner Example",
        password_hash="hashed-password-placeholder",
        is_active=True,
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


def make_membership(
    *,
    organisation_id: UUID,
    user_id: UUID,
    role: OrganisationRole,
) -> OrganisationMembership:
    return OrganisationMembership(
        id=uuid4(),
        organisation_id=organisation_id,
        user_id=user_id,
        role=role,
        created_at=NOW,
        updated_at=NOW,
    )


def make_api_key(
    *,
    organisation_id: UUID,
    raw_key: str,
    api_key_id: UUID | None = None,
    created_by_user_id: UUID | None = None,
    revoked_at: datetime | None = None,
) -> APIKey:
    key_secrets = APIKeySecretService()
    return APIKey(
        id=api_key_id or uuid4(),
        organisation_id=organisation_id,
        name="Demo automation",
        key_prefix=key_secrets.key_prefix(raw_key),
        key_hash=key_secrets.hash_key(raw_key),
        created_by_user_id=created_by_user_id,
        revoked_at=revoked_at,
        last_used_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_project(*, organisation_id: UUID, project_id: UUID | None = None) -> Project:
    return Project(
        id=project_id or uuid4(),
        organisation_id=organisation_id,
        name="Billing Portal",
        status=ProjectStatus.ACTIVE,
        description="Public-safe demo project",
        created_by_user_id=None,
        updated_by_user_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def test_owner_can_create_api_key_returns_raw_once_and_stores_only_hash() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.OWNER,
    )
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership])
    client = build_client(fake)

    response = client.post(
        f"/orgs/{organisation.id}/api-keys",
        json={"name": "Demo automation"},
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 201
    body = response.json()
    raw_key = body["raw_key"]
    key_secrets = APIKeySecretService()
    assert raw_key.startswith("saas_demo_")
    assert body["api_key"]["name"] == "Demo automation"
    assert body["api_key"]["key_prefix"] == key_secrets.key_prefix(raw_key)
    assert "raw_key" not in body["api_key"]
    assert "key_hash" not in response.text

    api_key = next(instance for instance in fake.added if isinstance(instance, APIKey))
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert api_key.key_hash == key_secrets.hash_key(raw_key)
    assert api_key.key_hash != raw_key
    assert api_key.key_prefix == key_secrets.key_prefix(raw_key)
    assert api_key.created_by_user_id == actor_user_id
    assert not hasattr(api_key, "raw_key")
    assert audit_event.action is AuditAction.API_KEY_CREATED
    assert audit_event.organisation_id == organisation.id
    assert audit_event.actor_user_id == actor_user_id
    assert audit_event.actor_api_key_id is None
    assert audit_event.target_type == "api_key"
    assert audit_event.target_id == api_key.id
    assert raw_key not in str(audit_event.event_metadata)
    assert "key_hash" not in str(audit_event.event_metadata)
    assert fake.committed == 1
    assert fake.rolled_back == 0

    metrics_text = client.get("/metrics").text
    assert "saas_api_api_keys_created_total 1.0" in metrics_text
    assert 'saas_api_audit_events_recorded_total{action="api_key.created"} 1.0' in metrics_text


def test_api_key_list_exposes_metadata_without_raw_key_or_hash() -> None:
    actor_user_id = uuid4()
    raw_key = APIKeySecretService().generate_raw_key()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.ADMIN,
    )
    api_key = make_api_key(
        organisation_id=organisation.id,
        raw_key=raw_key,
        created_by_user_id=actor_user_id,
    )
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership, 1])
    fake.scalars_results.append(FakeScalarResult([api_key]))
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/api-keys?limit=10&offset=0",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["id"] == str(api_key.id)
    assert body["items"][0]["key_prefix"] == api_key.key_prefix
    assert body["pagination"] == {"limit": 10, "offset": 0, "total": 1, "count": 1}
    assert raw_key not in response.text
    assert api_key.key_hash not in response.text
    assert "raw_key" not in body["items"][0]
    assert "key_hash" not in body["items"][0]


def test_member_cannot_create_api_keys() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.MEMBER,
    )
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership])
    client = build_client(fake)

    response = client.post(
        f"/orgs/{organisation.id}/api-keys",
        json={"name": "Demo automation"},
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "insufficient permissions for this organisation"}
    assert fake.added == []
    assert fake.committed == 0


def test_admin_can_revoke_api_key_and_records_audit_event() -> None:
    actor_user_id = uuid4()
    raw_key = APIKeySecretService().generate_raw_key()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.ADMIN,
    )
    api_key = make_api_key(
        organisation_id=organisation.id,
        raw_key=raw_key,
        created_by_user_id=actor_user_id,
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, membership, api_key]
    )
    client = build_client(fake)

    response = client.delete(
        f"/orgs/{organisation.id}/api-keys/{api_key.id}",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(api_key.id)
    assert body["organisation_id"] == str(organisation.id)
    assert body["status"] == "revoked"
    assert api_key.revoked_at is not None
    assert raw_key not in response.text
    assert api_key.key_hash not in response.text

    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert audit_event.action is AuditAction.API_KEY_REVOKED
    assert audit_event.organisation_id == organisation.id
    assert audit_event.actor_user_id == actor_user_id
    assert audit_event.actor_api_key_id is None
    assert audit_event.target_type == "api_key"
    assert audit_event.target_id == api_key.id
    assert raw_key not in str(audit_event.event_metadata)
    assert "key_hash" not in str(audit_event.event_metadata)
    assert fake.committed == 1

    metrics_text = client.get("/metrics").text
    assert "saas_api_api_keys_revoked_total 1.0" in metrics_text
    assert 'saas_api_audit_events_recorded_total{action="api_key.revoked"} 1.0' in metrics_text


def test_api_key_can_read_allowed_project_endpoint_and_updates_last_used() -> None:
    raw_key = APIKeySecretService().generate_raw_key()
    organisation = make_organisation()
    api_key = make_api_key(organisation_id=organisation.id, raw_key=raw_key)
    project = make_project(organisation_id=organisation.id)
    fake = FakeSession()
    fake.scalar_results.extend([api_key, 1])
    fake.scalars_results.append(FakeScalarResult([project]))
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/projects?limit=10&offset=0",
        headers=api_key_header(raw_key),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["id"] == str(project.id)
    assert body["items"][0]["organisation_id"] == str(organisation.id)
    assert raw_key not in response.text
    assert api_key.key_hash not in response.text
    assert api_key.last_used_at is not None
    assert fake.committed == 1
    active_lookup_sql = compile_sql(fake.scalar_statements[0])
    project_list_sql = compile_sql(fake.scalars_statements[0])
    assert "api_keys.key_hash" in active_lookup_sql
    assert "api_keys.revoked_at IS NULL" in active_lookup_sql
    assert "projects.organisation_id" in project_list_sql


def test_api_key_can_create_project_with_api_key_actor_audit() -> None:
    raw_key = APIKeySecretService().generate_raw_key()
    organisation = make_organisation()
    api_key = make_api_key(organisation_id=organisation.id, raw_key=raw_key)
    fake = FakeSession()
    fake.scalar_results.append(api_key)
    client = build_client(fake)

    response = client.post(
        f"/orgs/{organisation.id}/projects",
        json={"name": "Machine-created project", "status": "active"},
        headers=api_key_header(raw_key),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Machine-created project"
    assert body["organisation_id"] == str(organisation.id)
    assert body["created_by_user_id"] is None
    assert raw_key not in response.text

    project = next(instance for instance in fake.added if isinstance(instance, Project))
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert project.organisation_id == organisation.id
    assert project.created_by_user_id is None
    assert audit_event.action is AuditAction.PROJECT_CREATED
    assert audit_event.actor_user_id is None
    assert audit_event.actor_api_key_id == api_key.id
    assert audit_event.target_id == project.id
    assert raw_key not in str(audit_event.event_metadata)
    assert fake.committed == 2


def test_revoked_api_key_is_denied_for_project_endpoints() -> None:
    raw_key = APIKeySecretService().generate_raw_key()
    organisation = make_organisation()
    fake = FakeSession()
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/projects",
        headers=api_key_header(raw_key),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid or expired access token or API key"}
    assert fake.committed == 0
    active_lookup_sql = compile_sql(fake.scalar_statements[0])
    assert "api_keys.key_hash" in active_lookup_sql
    assert "api_keys.revoked_at IS NULL" in active_lookup_sql


def test_api_key_cannot_access_other_tenant_projects() -> None:
    raw_key = APIKeySecretService().generate_raw_key()
    organisation = make_organisation()
    other_organisation_id = uuid4()
    api_key = make_api_key(organisation_id=organisation.id, raw_key=raw_key)
    fake = FakeSession()
    fake.scalar_results.append(api_key)
    client = build_client(fake)

    response = client.get(
        f"/orgs/{other_organisation_id}/projects",
        headers=api_key_header(raw_key),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "organisation access denied"}
    assert raw_key not in response.text
    assert fake.scalars_statements == []
    assert len(fake.scalar_statements) == 1


def test_api_key_cannot_manage_members_or_api_keys() -> None:
    raw_key = APIKeySecretService().generate_raw_key()
    organisation = make_organisation()
    fake = FakeSession()
    client = build_client(fake)

    member_response = client.get(
        f"/orgs/{organisation.id}/members",
        headers=api_key_header(raw_key),
    )
    create_key_response = client.post(
        f"/orgs/{organisation.id}/api-keys",
        json={"name": "Nested key attempt"},
        headers=api_key_header(raw_key),
    )
    revoke_key_response = client.delete(
        f"/orgs/{organisation.id}/api-keys/{uuid4()}",
        headers=api_key_header(raw_key),
    )

    assert member_response.status_code == 401
    assert create_key_response.status_code == 401
    assert revoke_key_response.status_code == 401
    assert fake.added == []
    assert fake.scalar_statements == []
    assert fake.committed == 0
