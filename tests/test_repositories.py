from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ClauseElement

from multi_tenant_saas_api.database import (
    APIKey,
    AuditEvent,
    IdempotencyRecord,
    Organisation,
    OrganisationMembership,
    Project,
    User,
)
from multi_tenant_saas_api.domain import AuditAction, OrganisationRole, ProjectStatus
from multi_tenant_saas_api.repositories import (
    APIKeyRepository,
    AuditEventRepository,
    IdempotencyRecordRepository,
    MembershipRepository,
    OrganisationRepository,
    ProjectRepository,
    UserRepository,
)


class FakeScalarResult[ScalarT]:
    def __init__(self, values: Sequence[ScalarT]) -> None:
        self._values = list(values)

    def first(self) -> ScalarT | None:
        return self._values[0] if self._values else None

    def all(self) -> Sequence[ScalarT]:
        return self._values


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flushed = 0
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


def make_user(*, user_id: UUID | None = None, email: str = "user@example.com") -> User:
    return User(
        id=user_id or uuid4(),
        email=email,
        display_name="Example User",
        password_hash="hashed-password-placeholder",
    )


def make_organisation(*, organisation_id: UUID | None = None) -> Organisation:
    return Organisation(
        id=organisation_id or uuid4(),
        name="Acme Demo",
        slug="acme-demo",
    )


def test_user_repository_creates_and_fetches_users_without_raw_passwords() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        user_repository = UserRepository(as_session(fake))
        user_id = uuid4()
        stored_user = make_user(user_id=user_id)
        fake.scalar_results.extend([stored_user, stored_user])

        created = await user_repository.create(
            email="owner@example.com",
            display_name="Owner Example",
            password_hash="hashed-password-placeholder",
        )
        by_id = await user_repository.get_by_id(user_id)
        by_email = await user_repository.get_by_email("owner@example.com")

        assert created.password_hash == "hashed-password-placeholder"
        assert not hasattr(created, "raw_password")
        assert fake.added == [created]
        assert fake.flushed == 1
        assert by_id is stored_user
        assert by_email is stored_user
        assert "users.id" in compile_sql(fake.scalar_statements[0])
        assert "users.email" in compile_sql(fake.scalar_statements[1])

    asyncio.run(scenario())


def test_organisation_repository_lists_only_user_memberships_and_updates_metadata() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        organisation_repository = OrganisationRepository(as_session(fake))
        user_id = uuid4()
        organisation = make_organisation()
        fake.scalars_results.append(FakeScalarResult([organisation]))
        fake.scalar_results.extend([organisation, organisation, 3])

        created = await organisation_repository.create(name="Acme Demo", slug="acme-demo")
        organisations = await organisation_repository.list_for_user(
            user_id=user_id,
            limit=25,
            offset=5,
        )
        by_id = await organisation_repository.get_by_id(organisation.id)
        by_slug = await organisation_repository.get_by_slug("acme-demo")
        count = await organisation_repository.count_for_user(user_id)
        updated = await organisation_repository.update(
            created,
            name="Acme Demo Updated",
            slug="acme-demo-updated",
        )

        assert organisations == [organisation]
        assert by_id is organisation
        assert by_slug is organisation
        assert count == 3
        assert updated.name == "Acme Demo Updated"
        assert updated.slug == "acme-demo-updated"
        list_sql = compile_sql(fake.scalars_statements[0])
        by_id_sql = compile_sql(fake.scalar_statements[0])
        by_slug_sql = compile_sql(fake.scalar_statements[1])
        count_sql = compile_sql(fake.scalar_statements[2])
        assert "JOIN organisation_memberships" in list_sql
        assert "organisation_memberships.user_id" in list_sql
        assert "organisations.id" in by_id_sql
        assert "organisations.slug" in by_slug_sql
        assert "organisation_memberships.user_id" in count_sql

    asyncio.run(scenario())


def test_membership_repository_scopes_queries_and_supports_last_owner_checks() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        membership_repository = MembershipRepository(as_session(fake))
        organisation_id = uuid4()
        owner_user_id = uuid4()
        other_user_id = uuid4()
        owner_membership = OrganisationMembership(
            id=uuid4(),
            organisation_id=organisation_id,
            user_id=owner_user_id,
            role=OrganisationRole.OWNER,
        )
        fake.scalars_results.extend(
            [FakeScalarResult([owner_membership]), FakeScalarResult([owner_membership])]
        )
        fake.scalar_results.extend([1, 2, 1, owner_membership, 0])

        created = await membership_repository.create(
            organisation_id=organisation_id,
            user_id=owner_user_id,
            role=OrganisationRole.OWNER,
        )
        memberships = await membership_repository.list_for_organisation(
            organisation_id=organisation_id,
            limit=10,
        )
        user_memberships = await membership_repository.list_for_user(owner_user_id)
        organisation_count = await membership_repository.count_for_organisation(organisation_id)
        owner_count = await membership_repository.count_owners(organisation_id)
        has_other_owner = await membership_repository.has_other_owner(
            organisation_id=organisation_id,
            user_id=other_user_id,
        )
        is_last_owner = await membership_repository.is_last_owner(
            organisation_id=organisation_id,
            user_id=owner_user_id,
        )
        updated = await membership_repository.update_role(created, role=OrganisationRole.VIEWER)
        await membership_repository.delete(updated)

        assert memberships == [owner_membership]
        assert user_memberships == [owner_membership]
        assert organisation_count == 1
        assert owner_count == 2
        assert has_other_owner is True
        assert is_last_owner is True
        assert updated.role is OrganisationRole.VIEWER
        assert fake.deleted == [updated]
        list_sql = compile_sql(fake.scalars_statements[0])
        user_list_sql = compile_sql(fake.scalars_statements[1])
        organisation_count_sql = compile_sql(fake.scalar_statements[0])
        owner_count_sql = compile_sql(fake.scalar_statements[1])
        other_owner_sql = compile_sql(fake.scalar_statements[2])
        last_owner_membership_sql = compile_sql(fake.scalar_statements[3])
        last_owner_other_sql = compile_sql(fake.scalar_statements[4])
        assert "organisation_memberships.organisation_id" in list_sql
        assert "organisation_memberships.user_id" in user_list_sql
        assert "organisation_memberships.organisation_id" in organisation_count_sql
        assert "organisation_memberships.role" in owner_count_sql
        assert "organisation_memberships.user_id !=" in other_owner_sql
        assert "organisation_memberships.user_id" in last_owner_membership_sql
        assert "organisation_memberships.user_id !=" in last_owner_other_sql

    asyncio.run(scenario())


def test_project_repository_uses_tenant_scoped_queries_and_soft_delete() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        project_repository = ProjectRepository(as_session(fake))
        organisation_id = uuid4()
        project_id = uuid4()
        actor_user_id = uuid4()
        deleted_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        project = Project(
            id=project_id,
            organisation_id=organisation_id,
            name="Billing Portal",
            status=ProjectStatus.ACTIVE,
            description="Public-safe demo project",
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        fake.scalar_results.extend([project, 1])
        fake.scalars_results.append(FakeScalarResult([project]))

        created = await project_repository.create(
            organisation_id=organisation_id,
            name="Billing Portal",
            description="Public-safe demo project",
            created_by_user_id=actor_user_id,
        )
        fetched = await project_repository.get_by_id(
            organisation_id=organisation_id,
            project_id=project_id,
        )
        projects = await project_repository.list_for_organisation(
            organisation_id=organisation_id,
            status=ProjectStatus.ACTIVE,
            name_search="Billing",
            limit=20,
        )
        count = await project_repository.count_for_organisation(organisation_id=organisation_id)
        updated = await project_repository.update(
            created,
            description=None,
            status=ProjectStatus.ARCHIVED,
            updated_by_user_id=actor_user_id,
        )
        deleted = await project_repository.delete(
            updated,
            deleted_at=deleted_at,
            updated_by_user_id=actor_user_id,
        )

        assert fetched is project
        assert projects == [project]
        assert count == 1
        assert updated.description is None
        assert updated.status is ProjectStatus.ARCHIVED
        assert deleted.deleted_at == deleted_at
        get_sql = compile_sql(fake.scalar_statements[0])
        list_sql = compile_sql(fake.scalars_statements[0])
        count_sql = compile_sql(fake.scalar_statements[1])
        assert "projects.organisation_id" in get_sql
        assert "projects.id" in get_sql
        assert "projects.deleted_at IS NULL" in get_sql
        assert "projects.organisation_id" in list_sql
        assert "projects.status" in list_sql
        assert "projects.name" in list_sql
        assert "projects.organisation_id" in count_sql

    asyncio.run(scenario())


def test_api_key_repository_keeps_management_scoped_and_stores_only_hashes() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        api_key_repository = APIKeyRepository(as_session(fake))
        organisation_id = uuid4()
        api_key_id = uuid4()
        actor_user_id = uuid4()
        revoked_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        api_key = APIKey(
            id=api_key_id,
            organisation_id=organisation_id,
            name="Automation",
            key_prefix="saas_demo",
            key_hash="hashed-api-key-placeholder",
            created_by_user_id=actor_user_id,
        )
        fake.scalar_results.extend([api_key, api_key, 1])
        fake.scalars_results.append(FakeScalarResult([api_key]))

        created = await api_key_repository.create(
            organisation_id=organisation_id,
            name="Automation",
            key_prefix="saas_demo",
            key_hash="hashed-api-key-placeholder",
            created_by_user_id=actor_user_id,
        )
        fetched = await api_key_repository.get_by_id(
            organisation_id=organisation_id,
            api_key_id=api_key_id,
        )
        active = await api_key_repository.get_active_by_hash("hashed-api-key-placeholder")
        api_keys = await api_key_repository.list_for_organisation(
            organisation_id=organisation_id,
            include_revoked=False,
            limit=10,
        )
        count = await api_key_repository.count_for_organisation(
            organisation_id=organisation_id,
            include_revoked=False,
        )
        revoked = await api_key_repository.revoke(created, revoked_at=revoked_at)
        used = await api_key_repository.update_last_used(revoked, last_used_at=revoked_at)

        assert created.key_hash == "hashed-api-key-placeholder"
        assert not hasattr(created, "raw_key")
        assert fetched is api_key
        assert active is api_key
        assert api_keys == [api_key]
        assert count == 1
        assert revoked.revoked_at == revoked_at
        assert used.last_used_at == revoked_at
        scoped_get_sql = compile_sql(fake.scalar_statements[0])
        auth_lookup_sql = compile_sql(fake.scalar_statements[1])
        list_sql = compile_sql(fake.scalars_statements[0])
        count_sql = compile_sql(fake.scalar_statements[2])
        assert "api_keys.organisation_id" in scoped_get_sql
        assert "api_keys.key_hash" in auth_lookup_sql
        assert "api_keys.revoked_at IS NULL" in auth_lookup_sql
        assert "api_keys.organisation_id" in list_sql
        assert "api_keys.revoked_at IS NULL" in list_sql
        assert "api_keys.organisation_id" in count_sql

    asyncio.run(scenario())


def test_audit_event_repository_creates_and_lists_organisation_events() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        audit_repository = AuditEventRepository(as_session(fake))
        organisation_id = uuid4()
        actor_user_id = uuid4()
        target_id = uuid4()
        audit_event = AuditEvent(
            id=uuid4(),
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            action=AuditAction.PROJECT_CREATED,
            target_type="project",
            target_id=target_id,
            event_metadata={"project_name": "Billing Portal"},
        )
        fake.scalars_results.append(FakeScalarResult([audit_event]))
        fake.scalar_results.append(1)

        created = await audit_repository.create(
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            action=AuditAction.PROJECT_CREATED,
            target_type="project",
            target_id=target_id,
            event_metadata={"project_name": "Billing Portal"},
        )
        audit_events = await audit_repository.list_for_organisation(
            organisation_id=organisation_id,
            limit=10,
        )
        count = await audit_repository.count_for_organisation(organisation_id)

        assert created.event_metadata == {"project_name": "Billing Portal"}
        assert "password" not in created.event_metadata
        assert audit_events == [audit_event]
        assert count == 1
        list_sql = compile_sql(fake.scalars_statements[0])
        count_sql = compile_sql(fake.scalar_statements[0])
        assert "audit_events.organisation_id" in list_sql
        assert "audit_events.organisation_id" in count_sql

    asyncio.run(scenario())


def test_idempotency_repository_scopes_records_by_principal_request_and_tenant() -> None:
    async def scenario() -> None:
        fake = FakeSession()
        idempotency_repository = IdempotencyRecordRepository(as_session(fake))
        principal_id = uuid4()
        organisation_id = uuid4()
        record = IdempotencyRecord(
            id=uuid4(),
            principal_type="user",
            principal_id=principal_id,
            organisation_id=organisation_id,
            key="demo-idempotency-key",
            method="POST",
            path="/orgs/demo/projects",
            request_hash="request-body-hash-placeholder",
            response_status_code=201,
            response_body={"id": "project-id-placeholder"},
        )
        fake.scalar_results.extend([record, record])

        created = await idempotency_repository.create(
            principal_type="user",
            principal_id=principal_id,
            organisation_id=organisation_id,
            key="demo-idempotency-key",
            method="POST",
            path="/orgs/demo/projects",
            request_hash="request-body-hash-placeholder",
            response_status_code=201,
            response_body={"id": "project-id-placeholder"},
        )
        scoped_record = await idempotency_repository.get(
            principal_type="user",
            principal_id=principal_id,
            organisation_id=organisation_id,
            key="demo-idempotency-key",
            method="POST",
            path="/orgs/demo/projects",
        )
        unscoped_record = await idempotency_repository.get(
            principal_type="user",
            principal_id=principal_id,
            organisation_id=None,
            key="demo-idempotency-key",
            method="POST",
            path="/auth/register",
        )

        assert created.response_body == {"id": "project-id-placeholder"}
        assert scoped_record is record
        assert unscoped_record is record
        scoped_sql = compile_sql(fake.scalar_statements[0])
        unscoped_sql = compile_sql(fake.scalar_statements[1])
        for expected in (
            "idempotency_records.principal_type",
            "idempotency_records.principal_id",
            "idempotency_records.key",
            "idempotency_records.method",
            "idempotency_records.path",
        ):
            assert expected in scoped_sql
        assert "idempotency_records.organisation_id" in scoped_sql
        assert "idempotency_records.organisation_id IS NULL" in unscoped_sql

    asyncio.run(scenario())
