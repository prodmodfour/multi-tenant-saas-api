"""System endpoint routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.dependencies import get_readiness_service
from multi_tenant_saas_api.schemas.system import (
    DependencyReadinessResponse,
    HealthResponse,
    ReadinessResponse,
)
from multi_tenant_saas_api.services import DependencyReadiness, ReadinessResult, ReadinessService


def create_system_router(settings: Settings) -> APIRouter:
    """Create routes for system-level endpoints."""

    router = APIRouter(tags=["system"])

    @router.get("/healthz", response_model=HealthResponse, summary="Health check")
    async def healthz() -> HealthResponse:
        """Return a lightweight liveness response."""

        return HealthResponse(
            status="ok",
            app_name=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        )

    @router.get(
        "/readyz",
        response_model=ReadinessResponse,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
        summary="Readiness check",
    )
    async def readyz(
        response: Response,
        readiness_service: Annotated[ReadinessService, Depends(get_readiness_service)],
    ) -> ReadinessResponse:
        """Return dependency readiness, including a PostgreSQL round trip."""

        readiness = await readiness_service.check_readiness()
        if not readiness.is_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return _readiness_response(readiness)

    return router


def _readiness_response(readiness: ReadinessResult) -> ReadinessResponse:
    """Convert service-layer readiness data to the API response schema."""

    return ReadinessResponse(
        status=readiness.status,
        checks={check.name: _dependency_response(check) for check in readiness.checks},
    )


def _dependency_response(check: DependencyReadiness) -> DependencyReadinessResponse:
    """Convert a dependency readiness check to its response schema."""

    return DependencyReadinessResponse(status=check.status, detail=check.detail)
