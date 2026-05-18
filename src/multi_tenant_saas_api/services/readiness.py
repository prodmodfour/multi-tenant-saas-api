"""Application readiness checks for external dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from multi_tenant_saas_api.repositories import DatabaseReadinessRepository

ReadinessStatus = Literal["ready", "not_ready"]
ReadinessDependencyStatus = Literal["ok", "unavailable"]


class ReadinessServiceError(ValueError):
    """Base class for readiness service configuration errors."""


class ReadinessServiceConfigurationError(ReadinessServiceError):
    """Raised when a readiness service has no database check collaborator."""


class DatabaseReadinessCheck(Protocol):
    """Protocol for the database readiness repository collaborator."""

    async def check_postgresql(self) -> None:
        """Run a minimal PostgreSQL readiness query."""
        ...


@dataclass(frozen=True, slots=True)
class DependencyReadiness:
    """Readiness state for one external dependency."""

    name: str
    status: ReadinessDependencyStatus
    detail: str


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    """Aggregate application readiness state."""

    status: ReadinessStatus
    checks: tuple[DependencyReadiness, ...]

    @property
    def is_ready(self) -> bool:
        """Return whether all dependency checks are ready."""

        return self.status == "ready"


class ReadinessService:
    """Run dependency checks needed before the API receives traffic."""

    __slots__ = ("_database_readiness",)

    def __init__(
        self,
        *,
        session: AsyncSession | None = None,
        database_readiness: DatabaseReadinessCheck | None = None,
    ) -> None:
        """Initialise readiness checks with a repository collaborator."""

        if database_readiness is None:
            if session is None:
                raise ReadinessServiceConfigurationError(
                    "readiness checks require a database session or repository"
                )
            database_readiness = DatabaseReadinessRepository(session)
        self._database_readiness = database_readiness

    async def check_readiness(self) -> ReadinessResult:
        """Return aggregate readiness for the application dependencies."""

        postgresql = await self._check_postgresql()
        status: ReadinessStatus = "ready" if postgresql.status == "ok" else "not_ready"
        return ReadinessResult(status=status, checks=(postgresql,))

    async def _check_postgresql(self) -> DependencyReadiness:
        """Run the PostgreSQL readiness check without exposing connection details."""

        try:
            await self._database_readiness.check_postgresql()
        except SQLAlchemyError:
            return DependencyReadiness(
                name="postgresql",
                status="unavailable",
                detail="PostgreSQL readiness check failed",
            )
        return DependencyReadiness(
            name="postgresql",
            status="ok",
            detail="PostgreSQL responded successfully",
        )


__all__ = [
    "DependencyReadiness",
    "ReadinessDependencyStatus",
    "ReadinessResult",
    "ReadinessService",
    "ReadinessServiceConfigurationError",
    "ReadinessServiceError",
    "ReadinessStatus",
]
