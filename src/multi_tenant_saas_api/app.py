"""FastAPI application factory."""

from fastapi import FastAPI

from multi_tenant_saas_api.config import Settings, get_settings
from multi_tenant_saas_api.logging_config import configure_logging
from multi_tenant_saas_api.middleware import install_request_id_middleware
from multi_tenant_saas_api.routes.system import create_system_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    docs_url = "/docs" if app_settings.docs_enabled else None
    redoc_url = "/redoc" if app_settings.docs_enabled else None
    openapi_url = "/openapi.json" if app_settings.docs_enabled else None

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
    )
    app.state.settings = app_settings

    install_request_id_middleware(app)
    app.include_router(create_system_router(app_settings))

    return app
