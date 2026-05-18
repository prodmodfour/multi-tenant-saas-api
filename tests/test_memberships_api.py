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
from multi_tenant_saas_api.services import AccessTokenService

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-membership-api"
JWT_ISSUER = "multi-tenant-saas-api-membership-api-test"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeScalarResult[ScalarT]:
    def __init__(self, values: Sequence[ScalarT]) -> None:
        self._values = list(values)

    def all(self) -> Sequence[ScalarT]:
        return self._values


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.committed = 0
        self.flushed = 0
        self.rolled_back = 0
        self.scalar_results: list[object | None] = []
        self.scalars_results: list[FakeScalarResult[object]] = []
        self.scalar_statements: list[ClauseElement] = []
        self.scalars_statements: list[ClauseElement] = []

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def delete(self, instance: object) -> None:
        self.deleted.append(instance)

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


def make_user(
    *,
    user_id: UUID | None = None,
    email: str = "owner@example.com",
    display_name: str = "Owner Example",
    is_active: bool = True,
) -> User:
    return User(
        id=user_id or uuid4(),
        email=email,
        display_name=display_name,
        password_hash="hashed-password-placeholder",
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


def test_list_members_returns_public_user_data_for_owner() -> None:
    actor_user_id = uuid4()
    target_user_id = uuid4()
    organisation = make_organisation()
    actor_membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.OWNER,
    )
    target_membership = make_membership(
        organisation_id=organisation.id,
        user_id=target_user_id,
        role=OrganisationRole.MEMBER,
    )
    target_user = make_user(
        user_id=target_user_id,
        email="member@example.com",
        display_name="Member Example",
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, actor_membership, target_user, 1]
    )
    fake.scalars_results.append(FakeScalarResult([target_membership]))
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/members?limit=10&offset=0",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": str(target_membership.id),
                "organisation_id": str(organisation.id),
                "user": {
                    "id": str(target_user_id),
                    "email": "member@example.com",
                    "display_name": "Member Example",
                    "is_active": True,
                },
                "role": "member",
                "created_at": NOW.isoformat().replace("+00:00", "Z"),
                "updated_at": NOW.isoformat().replace("+00:00", "Z"),
            }
        ],
        "pagination": {"limit": 10, "offset": 0, "total": 1, "count": 1},
    }
    assert "password" not in response.text.lower()
    list_sql = compile_sql(fake.scalars_statements[0])
    assert "organisation_memberships.organisation_id" in list_sql


def test_admin_can_add_member_and_records_secret_safe_audit_event() -> None:
    actor_user_id = uuid4()
    target_user_id = uuid4()
    organisation = make_organisation()
    actor_membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.ADMIN,
    )
    target_user = make_user(
        user_id=target_user_id,
        email="new-member@example.com",
        display_name="New Member",
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, actor_membership, target_user, None]
    )
    client = build_client(fake)

    response = client.post(
        f"/orgs/{organisation.id}/members",
        json={"user_id": str(target_user_id), "role": "member"},
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["id"] == str(target_user_id)
    assert body["user"]["email"] == "new-member@example.com"
    assert body["role"] == "member"
    assert "password" not in response.text.lower()

    created_membership = next(
        instance for instance in fake.added if isinstance(instance, OrganisationMembership)
    )
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert created_membership.organisation_id == organisation.id
    assert created_membership.user_id == target_user_id
    assert created_membership.role is OrganisationRole.MEMBER
    assert audit_event.action is AuditAction.MEMBER_ADDED
    assert audit_event.organisation_id == organisation.id
    assert audit_event.actor_user_id == actor_user_id
    assert audit_event.target_type == "membership"
    assert audit_event.target_id == created_membership.id
    assert audit_event.event_metadata == {"user_id": str(target_user_id), "role": "member"}
    assert fake.committed == 1
    assert fake.rolled_back == 0


def test_owner_can_update_member_role_and_records_audit_event() -> None:
    actor_user_id = uuid4()
    target_user_id = uuid4()
    organisation = make_organisation()
    actor_membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.OWNER,
    )
    target_membership = make_membership(
        organisation_id=organisation.id,
        user_id=target_user_id,
        role=OrganisationRole.MEMBER,
    )
    target_user = make_user(
        user_id=target_user_id,
        email="member@example.com",
        display_name="Member Example",
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [
            make_user(user_id=actor_user_id),
            organisation,
            actor_membership,
            target_membership,
            target_user,
        ]
    )
    client = build_client(fake)

    response = client.patch(
        f"/orgs/{organisation.id}/members/{target_user_id}",
        json={"role": "admin"},
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["user"]["id"] == str(target_user_id)
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert audit_event.action is AuditAction.MEMBER_ROLE_CHANGED
    assert audit_event.target_id == target_membership.id
    assert audit_event.event_metadata == {
        "user_id": str(target_user_id),
        "old_role": "member",
        "new_role": "admin",
    }
    assert fake.committed == 1


def test_owner_can_remove_member_and_records_audit_event() -> None:
    actor_user_id = uuid4()
    target_user_id = uuid4()
    organisation = make_organisation()
    actor_membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.OWNER,
    )
    target_membership = make_membership(
        organisation_id=organisation.id,
        user_id=target_user_id,
        role=OrganisationRole.ADMIN,
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, actor_membership, target_membership]
    )
    client = build_client(fake)

    response = client.delete(
        f"/orgs/{organisation.id}/members/{target_user_id}",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 204
    assert response.content == b""
    assert fake.deleted == [target_membership]
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert audit_event.action is AuditAction.MEMBER_REMOVED
    assert audit_event.organisation_id == organisation.id
    assert audit_event.actor_user_id == actor_user_id
    assert audit_event.target_id == target_membership.id
    assert audit_event.event_metadata == {"user_id": str(target_user_id), "role": "admin"}
    assert fake.committed == 1


def test_last_owner_protection_blocks_removing_the_final_owner() -> None:
    owner_user_id = uuid4()
    organisation = make_organisation()
    owner_membership = make_membership(
        organisation_id=organisation.id,
        user_id=owner_user_id,
        role=OrganisationRole.OWNER,
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [
            make_user(user_id=owner_user_id),
            organisation,
            owner_membership,
            owner_membership,
            owner_membership,
            0,
        ]
    )
    client = build_client(fake)

    response = client.delete(
        f"/orgs/{organisation.id}/members/{owner_user_id}",
        headers=bearer_header(owner_user_id),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "organisation must always have at least one owner"}
    assert fake.deleted == []
    assert fake.added == []
    assert fake.committed == 0


def test_member_and_viewer_cannot_manage_members() -> None:
    for role in (OrganisationRole.MEMBER, OrganisationRole.VIEWER):
        actor_user_id = uuid4()
        organisation = make_organisation()
        actor_membership = make_membership(
            organisation_id=organisation.id,
            user_id=actor_user_id,
            role=role,
        )
        fake = FakeSession()
        fake.scalar_results.extend(
            [make_user(user_id=actor_user_id), organisation, actor_membership]
        )
        client = build_client(fake)

        response = client.get(
            f"/orgs/{organisation.id}/members",
            headers=bearer_header(actor_user_id),
        )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient permissions for this organisation"}
        assert fake.scalars_statements == []
        assert fake.added == []
        assert fake.committed == 0


def test_cross_tenant_member_management_is_denied() -> None:
    actor_user_id = uuid4()
    target_user_id = uuid4()
    organisation = make_organisation()
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, None])
    client = build_client(fake)

    response = client.post(
        f"/orgs/{organisation.id}/members",
        json={"user_id": str(target_user_id), "role": "member"},
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "organisation access denied"}
    assert fake.added == []
    assert fake.committed == 0


def test_admin_cannot_grant_or_remove_owner_role() -> None:
    actor_user_id = uuid4()
    target_user_id = uuid4()
    organisation = make_organisation()
    actor_membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.ADMIN,
    )
    owner_membership = make_membership(
        organisation_id=organisation.id,
        user_id=target_user_id,
        role=OrganisationRole.OWNER,
    )

    grant_owner_fake = FakeSession()
    grant_owner_fake.scalar_results.extend(
        [
            make_user(user_id=actor_user_id),
            organisation,
            actor_membership,
            make_user(user_id=target_user_id),
            None,
        ]
    )
    grant_owner_client = build_client(grant_owner_fake)
    grant_owner_response = grant_owner_client.post(
        f"/orgs/{organisation.id}/members",
        json={"user_id": str(target_user_id), "role": "owner"},
        headers=bearer_header(actor_user_id),
    )

    remove_owner_fake = FakeSession()
    remove_owner_fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, actor_membership, owner_membership]
    )
    remove_owner_client = build_client(remove_owner_fake)
    remove_owner_response = remove_owner_client.delete(
        f"/orgs/{organisation.id}/members/{target_user_id}",
        headers=bearer_header(actor_user_id),
    )

    assert grant_owner_response.status_code == 403
    assert remove_owner_response.status_code == 403
    assert grant_owner_response.json() == remove_owner_response.json()
    assert grant_owner_response.json() == {
        "detail": "insufficient permissions for this organisation"
    }
    assert grant_owner_fake.added == []
    assert remove_owner_fake.deleted == []
    assert grant_owner_fake.committed == 0
    assert remove_owner_fake.committed == 0
