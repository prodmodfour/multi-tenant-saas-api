from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import SQLAlchemyError

from multi_tenant_saas_api.services import ReadinessService, ReadinessServiceConfigurationError


class FakeDatabaseReadiness:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def check_postgresql(self) -> None:
        self.calls += 1
        if self.fail:
            raise SQLAlchemyError("database connection details must not leak")


def test_readiness_service_reports_postgresql_ready() -> None:
    async def scenario() -> None:
        database_readiness = FakeDatabaseReadiness()
        service = ReadinessService(database_readiness=database_readiness)

        result = await service.check_readiness()

        assert result.is_ready is True
        assert result.status == "ready"
        assert result.checks[0].name == "postgresql"
        assert result.checks[0].status == "ok"
        assert result.checks[0].detail == "PostgreSQL responded successfully"
        assert database_readiness.calls == 1

    asyncio.run(scenario())


def test_readiness_service_reports_postgresql_unavailable_without_leaking_exception() -> None:
    async def scenario() -> None:
        database_readiness = FakeDatabaseReadiness(fail=True)
        service = ReadinessService(database_readiness=database_readiness)

        result = await service.check_readiness()

        assert result.is_ready is False
        assert result.status == "not_ready"
        assert result.checks[0].name == "postgresql"
        assert result.checks[0].status == "unavailable"
        assert result.checks[0].detail == "PostgreSQL readiness check failed"
        assert "database connection details" not in result.checks[0].detail
        assert database_readiness.calls == 1

    asyncio.run(scenario())


def test_readiness_service_requires_session_or_repository() -> None:
    with pytest.raises(ReadinessServiceConfigurationError):
        ReadinessService()
