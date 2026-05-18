"""System endpoint routes."""

from fastapi import APIRouter

from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.schemas.system import HealthResponse


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

    return router
