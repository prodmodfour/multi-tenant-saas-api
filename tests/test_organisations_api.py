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

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-org-api"
JWT_ISSUER = "multi-tenant-saas-api-org-api-test"
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


def make_organisation(
    *,
    organisation_id: UUID | None = None,
    name: str = "Acme Demo",
    slug: str = "acme-demo",
) -> Organisation:
    return Organisation(
        id=organisation_id or uuid4(),
        name=name,
        slug=slug,
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


def test_create_org_makes_creator_owner_and_records_audit_event() -> None:
    user_id = uuid4()
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=user_id), None])
    client = build_client(fake)

    response = client.post(
        "/orgs",
        json={"name": "Acme Demo"},
        headers=bearer_header(user_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme Demo"
    assert body["slug"] == "acme-demo"
    assert "password" not in response.text.lower()

    organisation = next(instance for instance in fake.added if isinstance(instance, Organisation))
    owner_membership = next(
        instance for instance in fake.added if isinstance(instance, OrganisationMembership)
    )
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))

    assert UUID(body["id"]) == organisation.id
    assert owner_membership.organisation_id == organisation.id
    assert owner_membership.user_id == user_id
    assert owner_membership.role is OrganisationRole.OWNER
    assert audit_event.action is AuditAction.ORGANISATION_CREATED
    assert audit_event.organisation_id == organisation.id
    assert audit_event.actor_user_id == user_id
    assert audit_event.target_type == "organisation"
    assert audit_event.target_id == organisation.id
    assert audit_event.event_metadata == {}
    assert fake.committed == 1
    assert fake.rolled_back == 0

    metrics_text = client.get("/metrics").text
    assert "saas_api_organisations_created_total 1.0" in metrics_text
    assert 'saas_api_audit_events_recorded_total{action="organisation.created"} 1.0' in metrics_text


def test_list_orgs_returns_only_current_user_memberships() -> None:
    user_id = uuid4()
    member_organisation = make_organisation(name="Member Org", slug="member-org")
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=user_id), 1])
    fake.scalars_results.append(FakeScalarResult([member_organisation]))
    client = build_client(fake)

    response = client.get(
        "/orgs?limit=10&offset=0",
        headers=bearer_header(user_id),
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": str(member_organisation.id),
                "name": "Member Org",
                "slug": "member-org",
                "created_at": NOW.isoformat().replace("+00:00", "Z"),
                "updated_at": NOW.isoformat().replace("+00:00", "Z"),
            }
        ],
        "pagination": {"limit": 10, "offset": 0, "total": 1, "count": 1},
    }
    list_sql = compile_sql(fake.scalars_statements[0])
    count_sql = compile_sql(fake.scalar_statements[1])
    assert "JOIN organisation_memberships" in list_sql
    assert "organisation_memberships.user_id" in list_sql
    assert "organisation_memberships.user_id" in count_sql


def test_get_org_enforces_tenant_membership_and_denies_cross_tenant_access() -> None:
    user_id = uuid4()
    organisation = make_organisation()
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=user_id), organisation, None])
    client = build_client(fake)

    response = client.get(f"/orgs/{organisation.id}", headers=bearer_header(user_id))

    assert response.status_code == 403
    assert response.json() == {"detail": "organisation access denied"}
    assert fake.committed == 0


def test_get_org_returns_metadata_for_members() -> None:
    user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=user_id,
        role=OrganisationRole.VIEWER,
    )
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=user_id), organisation, membership, organisation])
    client = build_client(fake)

    response = client.get(f"/orgs/{organisation.id}", headers=bearer_header(user_id))

    assert response.status_code == 200
    assert response.json()["id"] == str(organisation.id)
    assert response.json()["name"] == "Acme Demo"
    assert response.json()["slug"] == "acme-demo"


def test_update_org_is_allowed_for_owner_and_admin_and_records_audit_event() -> None:
    for role in (OrganisationRole.OWNER, OrganisationRole.ADMIN):
        user_id = uuid4()
        organisation = make_organisation()
        membership = make_membership(
            organisation_id=organisation.id,
            user_id=user_id,
            role=role,
        )
        fake = FakeSession()
        fake.scalar_results.extend(
            [make_user(user_id=user_id), organisation, membership, organisation]
        )
        client = build_client(fake)

        response = client.patch(
            f"/orgs/{organisation.id}",
            json={"name": "Acme Demo Updated"},
            headers=bearer_header(user_id),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Acme Demo Updated"
        audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
        assert audit_event.action is AuditAction.ORGANISATION_UPDATED
        assert audit_event.organisation_id == organisation.id
        assert audit_event.actor_user_id == user_id
        assert audit_event.target_type == "organisation"
        assert audit_event.target_id == organisation.id
        assert audit_event.event_metadata == {"changed_fields": ["name"]}
        assert fake.committed == 1


def test_update_org_is_denied_for_member_and_viewer() -> None:
    for role in (OrganisationRole.MEMBER, OrganisationRole.VIEWER):
        user_id = uuid4()
        organisation = make_organisation()
        membership = make_membership(
            organisation_id=organisation.id,
            user_id=user_id,
            role=role,
        )
        fake = FakeSession()
        fake.scalar_results.extend([make_user(user_id=user_id), organisation, membership])
        client = build_client(fake)

        response = client.patch(
            f"/orgs/{organisation.id}",
            json={"name": "Acme Demo Updated"},
            headers=bearer_header(user_id),
        )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient permissions for this organisation"}
        assert fake.added == []
        assert fake.committed == 0


def test_duplicate_slug_is_rejected_without_creating_an_organisation() -> None:
    user_id = uuid4()
    existing_organisation = make_organisation(slug="acme-demo")
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=user_id), existing_organisation])
    client = build_client(fake)

    response = client.post(
        "/orgs",
        json={"name": "Acme Demo", "slug": "acme-demo"},
        headers=bearer_header(user_id),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "organisation slug is already in use"}
    assert fake.added == []
    assert fake.committed == 0


def test_update_rejects_duplicate_slug() -> None:
    user_id = uuid4()
    organisation = make_organisation(slug="acme-demo")
    conflicting_organisation = make_organisation(slug="taken-demo")
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=user_id,
        role=OrganisationRole.OWNER,
    )
    fake = FakeSession()
    fake.scalar_results.extend(
        [
            make_user(user_id=user_id),
            organisation,
            membership,
            organisation,
            conflicting_organisation,
        ]
    )
    client = build_client(fake)

    response = client.patch(
        f"/orgs/{organisation.id}",
        json={"slug": "taken-demo"},
        headers=bearer_header(user_id),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "organisation slug is already in use"}
    assert fake.added == []
    assert fake.committed == 0
