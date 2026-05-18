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
    AuditEvent,
    Organisation,
    OrganisationMembership,
    Project,
    User,
)
from multi_tenant_saas_api.dependencies import get_session
from multi_tenant_saas_api.domain import AuditAction, OrganisationRole, ProjectStatus, UserID
from multi_tenant_saas_api.services import AccessTokenService

JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-project-api"
JWT_ISSUER = "multi-tenant-saas-api-project-api-test"
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


def make_project(
    *,
    organisation_id: UUID,
    project_id: UUID | None = None,
    name: str = "Billing Portal",
    status: ProjectStatus = ProjectStatus.ACTIVE,
    description: str | None = "Public-safe demo project",
    actor_user_id: UUID | None = None,
) -> Project:
    return Project(
        id=project_id or uuid4(),
        organisation_id=organisation_id,
        name=name,
        status=status,
        description=description,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
        created_at=NOW,
        updated_at=NOW,
    )


def test_member_can_create_project_and_records_audit_event() -> None:
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
        f"/orgs/{organisation.id}/projects",
        json={
            "name": "Billing Portal",
            "description": "Public-safe demo project",
            "status": "active",
        },
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Billing Portal"
    assert body["status"] == "active"
    assert body["description"] == "Public-safe demo project"
    assert body["created_by_user_id"] == str(actor_user_id)
    assert "password" not in response.text.lower()

    project = next(instance for instance in fake.added if isinstance(instance, Project))
    audit_event = next(instance for instance in fake.added if isinstance(instance, AuditEvent))
    assert UUID(body["id"]) == project.id
    assert project.organisation_id == organisation.id
    assert project.created_by_user_id == actor_user_id
    assert project.updated_by_user_id == actor_user_id
    assert audit_event.action is AuditAction.PROJECT_CREATED
    assert audit_event.organisation_id == organisation.id
    assert audit_event.actor_user_id == actor_user_id
    assert audit_event.target_type == "project"
    assert audit_event.target_id == project.id
    assert audit_event.event_metadata == {"project_name": "Billing Portal", "status": "active"}
    assert fake.committed == 1
    assert fake.rolled_back == 0

    metrics_text = client.get("/metrics").text
    assert "saas_api_projects_created_total 1.0" in metrics_text
    assert 'saas_api_audit_events_recorded_total{action="project.created"} 1.0' in metrics_text


def test_project_list_supports_pagination_filtering_sorting_and_viewer_reads() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.VIEWER,
    )
    project = make_project(organisation_id=organisation.id, actor_user_id=actor_user_id)
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership, 1])
    fake.scalars_results.append(FakeScalarResult([project]))
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/projects"
        "?limit=10&offset=0&status=active&name=Billing&sort_by=name&sort_direction=asc",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": str(project.id),
                "organisation_id": str(organisation.id),
                "name": "Billing Portal",
                "status": "active",
                "description": "Public-safe demo project",
                "created_by_user_id": str(actor_user_id),
                "updated_by_user_id": str(actor_user_id),
                "created_at": NOW.isoformat().replace("+00:00", "Z"),
                "updated_at": NOW.isoformat().replace("+00:00", "Z"),
            }
        ],
        "pagination": {"limit": 10, "offset": 0, "total": 1, "count": 1},
    }
    list_sql = compile_sql(fake.scalars_statements[0])
    count_sql = compile_sql(fake.scalar_statements[3])
    assert "projects.organisation_id" in list_sql
    assert "projects.status" in list_sql
    assert "projects.name" in list_sql
    assert "ORDER BY projects.name ASC" in list_sql
    assert "projects.deleted_at IS NULL" in list_sql
    assert "projects.status" in count_sql
    assert "projects.name" in count_sql


def test_get_update_and_delete_project_are_scoped_and_audited() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.ADMIN,
    )

    get_project = make_project(organisation_id=organisation.id, actor_user_id=actor_user_id)
    get_fake = FakeSession()
    get_fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, membership, get_project]
    )
    get_client = build_client(get_fake)
    get_response = get_client.get(
        f"/orgs/{organisation.id}/projects/{get_project.id}",
        headers=bearer_header(actor_user_id),
    )

    update_project = make_project(organisation_id=organisation.id, actor_user_id=actor_user_id)
    update_fake = FakeSession()
    update_fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, membership, update_project]
    )
    update_client = build_client(update_fake)
    update_response = update_client.patch(
        f"/orgs/{organisation.id}/projects/{update_project.id}",
        json={"name": "Billing Portal v2", "description": None, "status": "archived"},
        headers=bearer_header(actor_user_id),
    )

    delete_project = make_project(organisation_id=organisation.id, actor_user_id=actor_user_id)
    delete_fake = FakeSession()
    delete_fake.scalar_results.extend(
        [make_user(user_id=actor_user_id), organisation, membership, delete_project]
    )
    delete_client = build_client(delete_fake)
    delete_response = delete_client.delete(
        f"/orgs/{organisation.id}/projects/{delete_project.id}",
        headers=bearer_header(actor_user_id),
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == str(get_project.id)
    assert get_response.json()["organisation_id"] == str(organisation.id)

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Billing Portal v2"
    assert update_response.json()["status"] == "archived"
    assert update_response.json()["description"] is None
    update_audit_event = next(
        instance for instance in update_fake.added if isinstance(instance, AuditEvent)
    )
    assert update_audit_event.action is AuditAction.PROJECT_UPDATED
    assert update_audit_event.organisation_id == organisation.id
    assert update_audit_event.actor_user_id == actor_user_id
    assert update_audit_event.target_id == update_project.id
    assert update_audit_event.event_metadata == {
        "changed_fields": ["name", "description", "status"]
    }
    assert update_fake.committed == 1

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert delete_project.deleted_at is not None
    delete_audit_event = next(
        instance for instance in delete_fake.added if isinstance(instance, AuditEvent)
    )
    assert delete_audit_event.action is AuditAction.PROJECT_DELETED
    assert delete_audit_event.organisation_id == organisation.id
    assert delete_audit_event.actor_user_id == actor_user_id
    assert delete_audit_event.target_id == delete_project.id
    assert delete_audit_event.event_metadata == {"project_name": "Billing Portal"}
    assert delete_fake.committed == 1


def test_project_ids_from_other_organisations_are_not_accessible() -> None:
    actor_user_id = uuid4()
    organisation = make_organisation()
    membership = make_membership(
        organisation_id=organisation.id,
        user_id=actor_user_id,
        role=OrganisationRole.MEMBER,
    )
    other_project_id = uuid4()
    fake = FakeSession()
    fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership, None])
    client = build_client(fake)

    response = client.get(
        f"/orgs/{organisation.id}/projects/{other_project_id}",
        headers=bearer_header(actor_user_id),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "project was not found"}
    project_lookup_sql = compile_sql(fake.scalar_statements[3])
    assert "projects.organisation_id" in project_lookup_sql
    assert "projects.id" in project_lookup_sql
    assert fake.committed == 0


def test_viewer_cannot_create_update_or_delete_projects() -> None:
    for method in ("post", "patch", "delete"):
        actor_user_id = uuid4()
        organisation = make_organisation()
        project = make_project(organisation_id=organisation.id, actor_user_id=actor_user_id)
        membership = make_membership(
            organisation_id=organisation.id,
            user_id=actor_user_id,
            role=OrganisationRole.VIEWER,
        )
        fake = FakeSession()
        fake.scalar_results.extend([make_user(user_id=actor_user_id), organisation, membership])
        client = build_client(fake)

        if method == "post":
            response = client.post(
                f"/orgs/{organisation.id}/projects",
                json={"name": "Billing Portal"},
                headers=bearer_header(actor_user_id),
            )
        elif method == "patch":
            response = client.patch(
                f"/orgs/{organisation.id}/projects/{project.id}",
                json={"name": "Billing Portal v2"},
                headers=bearer_header(actor_user_id),
            )
        else:
            response = client.delete(
                f"/orgs/{organisation.id}/projects/{project.id}",
                headers=bearer_header(actor_user_id),
            )

        assert response.status_code == 403
        assert response.json() == {"detail": "insufficient permissions for this organisation"}
        assert fake.added == []
        assert fake.committed == 0
