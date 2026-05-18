from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine

from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.database import (
    APIKey,
    AuditEvent,
    Base,
    IdempotencyRecord,
    Organisation,
    OrganisationMembership,
    Project,
    User,
    create_database_engine,
    create_session_factory,
)
from multi_tenant_saas_api.domain import AuditAction, OrganisationRole, ProjectStatus


def test_metadata_defines_required_tables_and_columns() -> None:
    expected_columns = {
        "users": {
            "id",
            "email",
            "display_name",
            "password_hash",
            "is_active",
            "created_at",
            "updated_at",
        },
        "organisations": {"id", "name", "slug", "created_at", "updated_at"},
        "organisation_memberships": {
            "id",
            "organisation_id",
            "user_id",
            "role",
            "created_at",
            "updated_at",
        },
        "projects": {
            "id",
            "organisation_id",
            "name",
            "status",
            "description",
            "created_by_user_id",
            "updated_by_user_id",
            "deleted_at",
            "created_at",
            "updated_at",
        },
        "api_keys": {
            "id",
            "organisation_id",
            "name",
            "key_prefix",
            "key_hash",
            "created_by_user_id",
            "revoked_at",
            "last_used_at",
            "created_at",
            "updated_at",
        },
        "audit_events": {
            "id",
            "organisation_id",
            "actor_user_id",
            "actor_api_key_id",
            "action",
            "target_type",
            "target_id",
            "metadata",
            "created_at",
        },
        "idempotency_records": {
            "id",
            "principal_type",
            "principal_id",
            "organisation_id",
            "key",
            "method",
            "path",
            "request_hash",
            "response_status_code",
            "response_body",
            "created_at",
            "expires_at",
        },
    }

    assert set(Base.metadata.tables) == set(expected_columns)
    for table_name, column_names in expected_columns.items():
        assert set(Base.metadata.tables[table_name].columns.keys()) == column_names


def test_models_include_tenant_scoped_constraints_and_indexes() -> None:
    memberships = Base.metadata.tables["organisation_memberships"]
    projects = Base.metadata.tables["projects"]
    api_keys = Base.metadata.tables["api_keys"]
    audit_events = Base.metadata.tables["audit_events"]
    idempotency_records = Base.metadata.tables["idempotency_records"]

    membership_constraint_names = {constraint.name for constraint in memberships.constraints}
    assert "uq_membership_organisation_user" in membership_constraint_names

    assert "ix_projects_organisation_status_created" in {index.name for index in projects.indexes}
    assert "ix_api_keys_organisation_created" in {index.name for index in api_keys.indexes}
    assert "ix_audit_events_organisation_created" in {index.name for index in audit_events.indexes}

    idempotency_indexes = {str(index.name): index for index in idempotency_records.indexes}
    assert idempotency_indexes["uq_idempotency_records_with_organisation"].unique is True
    assert idempotency_indexes["uq_idempotency_records_without_organisation"].unique is True
    assert "ix_idempotency_records_organisation_created" in idempotency_indexes


def test_model_construction_uses_secret_safe_storage_fields() -> None:
    user_id = uuid4()
    organisation_id = uuid4()
    api_key_id = uuid4()

    user = User(
        id=user_id,
        email="user@example.com",
        display_name="Example User",
        password_hash="hashed-password-placeholder",
    )
    organisation = Organisation(
        id=organisation_id,
        name="Example Organisation",
        slug="example-organisation",
    )
    membership = OrganisationMembership(
        organisation_id=organisation_id,
        user_id=user_id,
        role=OrganisationRole.OWNER,
    )
    project = Project(
        organisation_id=organisation_id,
        name="Example Project",
        status=ProjectStatus.ACTIVE,
        created_by_user_id=user_id,
        updated_by_user_id=user_id,
    )
    api_key = APIKey(
        id=api_key_id,
        organisation_id=organisation_id,
        name="Automation",
        key_prefix="saas_123",
        key_hash="hashed-api-key-placeholder",
        created_by_user_id=user_id,
    )
    audit_event = AuditEvent(
        organisation_id=organisation_id,
        actor_user_id=user_id,
        actor_api_key_id=api_key_id,
        action=AuditAction.API_KEY_CREATED,
        target_type="api_key",
        target_id=api_key_id,
        event_metadata={"key_prefix": "saas_123"},
    )
    idempotency_record = IdempotencyRecord(
        principal_type="user",
        principal_id=user_id,
        organisation_id=organisation_id,
        key="demo-idempotency-key",
        method="POST",
        path="/orgs/example/projects",
        request_hash="request-body-hash-placeholder",
        response_status_code=201,
        response_body={"id": "project-id-placeholder"},
    )

    assert user.password_hash == "hashed-password-placeholder"
    assert organisation.slug == "example-organisation"
    assert membership.role is OrganisationRole.OWNER
    assert project.status is ProjectStatus.ACTIVE
    assert api_key.key_hash == "hashed-api-key-placeholder"
    assert not hasattr(api_key, "raw_key")
    assert audit_event.event_metadata == {"key_prefix": "saas_123"}
    assert idempotency_record.response_body == {"id": "project-id-placeholder"}


def test_async_engine_and_session_factory_use_configured_database_url() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://saas_api:placeholder@localhost:5432/saas_api_test"
    )
    engine = create_database_engine(settings)

    try:
        assert isinstance(engine, AsyncEngine)
        assert (
            engine.url.render_as_string(hide_password=False)
            == "postgresql+asyncpg://saas_api:placeholder@localhost:5432/saas_api_test"
        )
        session_factory = create_session_factory(engine)
        assert session_factory.kw["expire_on_commit"] is False
    finally:
        asyncio.run(engine.dispose())


def test_initial_alembic_migration_can_render_offline_sql(
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = Config("alembic.ini")

    command.upgrade(config, "head", sql=True)

    rendered_sql = capsys.readouterr().out
    for table_name in (
        "users",
        "organisations",
        "organisation_memberships",
        "projects",
        "api_keys",
        "audit_events",
        "idempotency_records",
    ):
        assert f"CREATE TABLE {table_name}" in rendered_sql
    assert "uq_idempotency_records_with_organisation" in rendered_sql
    assert "organisation_id IS NOT NULL" in rendered_sql
