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
