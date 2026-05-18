"""Schemas for system endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    app_name: str
    version: str
    environment: str


class DependencyReadinessResponse(BaseModel):
    """Readiness state for one external dependency."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "unavailable"]
    detail: str


class ReadinessResponse(BaseModel):
    """Response returned by the readiness endpoint."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "not_ready"]
    checks: dict[str, DependencyReadinessResponse]
