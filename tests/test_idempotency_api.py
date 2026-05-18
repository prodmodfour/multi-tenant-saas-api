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
    IdempotencyRecord,
    Organisation,
    OrganisationMembership,
    Project,
    User,
)
from multi_tenant_saas_api.dependencies import get_session
from multi_tenant_saas_api.domain import AuditAction, OrganisationRole, UserID
from multi_tenant_saas_api.services import AccessTokenService
from multi_tenant_saas_api.services.api_keys import APIKeySecretService

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-idempotency"
JWT_ISSUER = "multi-tenant-saas-api-idempotency-test"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
IDEMPOTENCY_HEADER = "Idempotency-Key"
REPLAY_HEADER = "Idempotency-Replayed"


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
            if not isinstance(instance, (AuditEvent, IdempotencyRecord)) and (
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


def bearer_header(user_id: UUID, *, idempotency_key: str) -> dict[str, str]:
    access_token = AccessTokenService.from_settings(make_settings()).create_access_token(
        UserID(user_id)
    )
    return {"Authorization": f"Bearer {access_token.token}", IDEMPOTENCY_HEADER: idempotency_key}


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


def make_idempotency_record(
    *,
    principal_id: UUID,
    key: str,
    method: str,
    path: str,
    request_hash: str,
    response_body: dict[str, object],
    organisation_id: UUID | None = None,
) -> IdempotencyRecord:
    return IdempotencyRecord(
        id=uuid4(),
        principal_type="user",
        principal_id=principal_id,
        organisation_id=organisation_id,
        key=key,
        method=method,
        path=path,
        request_hash=request_hash,
        response_status_code=201,
        response_body=response_body,
        created_at=NOW,
    )


def test_post_org_replays_stored_response_for_same_principal_key_and_body() -> None:
    actor_user_id = uuid4()
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), None, None])
    client = build_client(fake)
    headers = bearer_header(actor_user_id, idempotency_key="create-org-once")

    first_response = client.post("/orgs", json={"name": "Acme Demo"}, headers=headers)

    assert first_response.status_code == 201
    record = next(instance for instance in fake.added if isinstance(instance, IdempotencyRecord))
    assert record.principal_type == "user"
    assert record.principal_id == actor_user_id
    assert record.organisation_id is None
    assert record.method == "POST"
    assert record.path == "/orgs"
    assert record.response_body == first_response.json()
    assert fake.committed == 2

    fake.scalar_results.extend([make_user(user_id=actor_user_id), record])
    replay_response = client.post("/orgs", json={"name": "Acme Demo"}, headers=headers)

    assert replay_response.status_code == 201
    assert replay_response.headers[REPLAY_HEADER] == "true"
    assert replay_response.json() == first_response.json()
    assert sum(isinstance(instance, Organisation) for instance in fake.added) == 1
    assert fake.committed == 2

    metrics_text = client.get("/metrics").text
    assert "saas_api_idempotency_replays_total 1.0" in metrics_text


def test_idempotency_key_reused_with_different_body_returns_conflict() -> None:
    actor_user_id = uuid4()
    existing_record = make_idempotency_record(
        principal_id=actor_user_id,
        key="create-org-conflict",
        method="POST",
        path="/orgs",
        request_hash="previous-request-body-hash",
        response_body={"id": "stored-organisation-id"},
    )
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), existing_record])
    client = build_client(fake)

    response = client.post(
        "/orgs",
        json={"name": "Changed Demo"},
        headers=bearer_header(actor_user_id, idempotency_key="create-org-conflict"),
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "idempotency key was already used with a different request body"
    }
    assert "request_hash" not in response.text
    assert fake.added == []
    assert fake.committed == 0

    metrics_text = client.get("/metrics").text
    assert "saas_api_idempotency_conflicts_total 1.0" in metrics_text


def test_project_idempotency_records_are_scoped_to_the_organisation() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.MEMBER,
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [
            make_user(user_id=actor_user_id),
            organisation,
            membership,
            None,
            organisation,
            membership,
        ]
    )
    client = build_client(fake)

    response = client.post(
        f"/orgs/{organisation.id}/projects",
        json={"name": "Billing Portal", "status": "active"},
        headers=bearer_header(actor_user_id, idempotency_key="create-project-once"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["organisation_id"] == str(organisation.id)
    record = next(instance for instance in fake.added if isinstance(instance, IdempotencyRecord))
    assert record.principal_id == actor_user_id
    assert record.organisation_id == organisation.id
    assert record.response_body == body
    idempotency_lookup_sql = compile_sql(fake.scalar_statements[3])
    assert "idempotency_records.organisation_id" in idempotency_lookup_sql
    assert "idempotency_records.principal_id" in idempotency_lookup_sql

    project = next(instance for instance in fake.added if isinstance(instance, Project))
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert project.organisation_id == organisation.id
    assert audit_event.action is AuditAction.PROJECT_CREATED
    assert fake.committed == 2


def test_api_key_idempotency_replay_does_not_store_or_return_raw_key_material() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.OWNER,
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [
            make_user(user_id=actor_user_id),
            organisation,
            membership,
            None,
            organisation,
            membership,
        ]
    )
    client = build_client(fake)
    headers = bearer_header(actor_user_id, idempotency_key="create-api-key-once")

    first_response = client.post(
        f"/orgs/{organisation.id}/api-keys",
        json={"name": "Demo automation"},
        headers=headers,
    )

    assert first_response.status_code == 201
    raw_key = first_response.json()["raw_key"]
    api_key = next(instance for instance in fake.added if isinstance(instance, APIKey))
    record = next(instance for instance in fake.added if isinstance(instance, IdempotencyRecord))
    assert raw_key.startswith("saas_demo_")
    assert api_key.key_hash == APIKeySecretService().hash_key(raw_key)
    assert "raw_key" not in record.response_body
    assert raw_key not in str(record.response_body)
    assert api_key.key_hash not in str(record.response_body)
    assert record.response_body["idempotency_replay"] == {
        "secret_available": False,
        "reason": (
            "raw API key material is returned only by the initial create response "
            "and is not replayed"
        ),
    }
    assert fake.committed == 2

    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership, record])
    replay_response = client.post(
        f"/orgs/{organisation.id}/api-keys",
        json={"name": "Demo automation"},
        headers=headers,
    )

    assert replay_response.status_code == 201
    assert replay_response.headers[REPLAY_HEADER] == "true"
    assert "raw_key" not in replay_response.json()
    assert raw_key not in replay_response.text
    assert api_key.key_hash not in replay_response.text
    assert replay_response.json()["idempotency_replay"]["secret_available"] is False
    assert sum(isinstance(instance, APIKey) for instance in fake.added) == 1
    assert fake.committed == 2
