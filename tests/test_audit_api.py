from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pydantic import SecretStr
from pytest import mark, raises
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ClauseElement

from multi_tenant_saas_api.app import create_app
from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.database import AuditEvent, Organisation, OrganisationMembership, User
from multi_tenant_saas_api.dependencies import get_session
from multi_tenant_saas_api.domain import AuditAction, OrganisationRole, UserID
from multi_tenant_saas_api.services import AccessTokenService
from multi_tenant_saas_api.services.audit import AuditMetadataRejectedError, AuditService

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-audit-api"
JWT_ISSUER = "multi-tenant-saas-api-audit-api-test"
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


def make_audit_event(
    *,
    organisation_id: UUID,
    actor_user_id: UUID,
    target_id: UUID | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=uuid4(),
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        actor_api_key_id=None,
        action=AuditAction.PROJECT_CREATED,
        target_type="project",
        target_id=target_id or uuid4(),
        event_metadata={"project_name": "Billing Portal", "status": "active"},
        created_at=NOW,
    )


def test_audit_service_records_core_operation_without_commit_and_rejects_secrets() -> None:
    async def scenario() -> None:
        organisation_id = uuid4()
        actor_user_id = uuid4()
        target_id = uuid4()
        fake = FakeSession()
        audit_service = AuditService(session=as_session(fake))

        audit_event = await audit_service.record_event(
            action=AuditAction.PROJECT_CREATED,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            target_type="project",
            target_id=target_id,
            metadata={"project_name": "Billing Portal", "status": "active"},
        )

        assert audit_event.organisation_id == organisation_id
        assert audit_event.actor_user_id == actor_user_id
        assert audit_event.action is AuditAction.PROJECT_CREATED
        assert audit_event.metadata == {"project_name": "Billing Portal", "status": "active"}
        stored_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
        assert stored_event.event_metadata == audit_event.metadata
        assert fake.flushed == 1
        assert fake.committed == 0

        forbidden_metadata_examples = (
            {"raw_key": "must-not-be-audited"},
            {"raw_api_key": "must-not-be-audited"},
            {"api_key": "must-not-be-audited"},
            {"login-token": "must-not-be-audited"},
            {"nested": {"jwt secret": "must-not-be-audited"}},
        )
        for metadata in forbidden_metadata_examples:
            with raises(AuditMetadataRejectedError):
                await audit_service.record_event(
                    action=AuditAction.API_KEY_CREATED,
                    organisation_id=organisation_id,
                    actor_user_id=actor_user_id,
                    target_type="api_key",
                    target_id=uuid4(),
                    metadata=metadata,
                )

    asyncio.run(scenario())


@mark.parametrize("role", [OrganisationRole.OWNER, OrganisationRole.ADMIN])
def test_owner_and_admin_can_read_paginated_audit_events(role: OrganisationRole) -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=role,
    )
    audit_event = make_audit_event(organisation_id=organisation.id, actor_user_id=actor_user_id)
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership, 2])
    fake.scalars_results.append(FakeScalarResult([audit_event]))
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/audit-events?limit=1&offset=1",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"] == {"limit": 1, "offset": 1, "total": 2, "count": 1}
    assert body["items"][0]["id"] == str(audit_event.id)
    assert body["items"][0]["organisation_id"] == str(organisation.id)
    assert body["items"][0]["actor_user_id"] == str(actor_user_id)
    assert body["items"][0]["action"] == "project.created"
    assert body["items"][0]["metadata"] == {
        "project_name": "Billing Portal",
        "status": "active",
    }
    for forbidden in ("password", "password_hash", "raw_key", "key_hash", "bearer"):
        assert forbidden not in response.text.lower()
    assert fake.committed == 0
    assert "audit_events.organisation_id" in compile_sql(fake.scalars_statements[0])
    assert "audit_events.organisation_id" in compile_sql(fake.scalar_statements[-1])


@mark.parametrize("role", [OrganisationRole.MEMBER, OrganisationRole.VIEWER])
def test_member_and_viewer_audit_read_policy_is_denied(role: OrganisationRole) -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=role,
    )
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership])
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/audit-events",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "insufficient permissions for this organisation"}
    assert fake.scalars_statements == []


def test_cross_tenant_audit_read_is_denied_before_listing_events() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, None])
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/audit-events",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "organisation access denied"}
    assert fake.scalars_statements == []
