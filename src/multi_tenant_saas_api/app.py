"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from multi_tenant_saas_api.config import Settings, get_settings
from multi_tenant_saas_api.database import create_database_engine, create_session_factory
from multi_tenant_saas_api.logging_config import configure_logging
from multi_tenant_saas_api.middleware import install_request_id_middleware
from multi_tenant_saas_api.routes.auth import create_auth_router
from multi_tenant_saas_api.routes.memberships import create_membership_router
from multi_tenant_saas_api.routes.organisations import create_organisation_router
from multi_tenant_saas_api.routes.system import create_system_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    docs_url = "/docs" if app_settings.docs_enabled else None
    redoc_url = "/redoc" if app_settings.docs_enabled else None
    openapi_url = "/openapi.json" if app_settings.docs_enabled else None

    database_engine = create_database_engine(app_settings)
    session_factory = create_session_factory(database_engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await database_engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.session_factory = session_factory

    install_request_id_middleware(app)
    app.include_router(create_system_router(app_settings))
    app.include_router(create_auth_router())
    app.include_router(create_organisation_router())
    app.include_router(create_membership_router())

    return app
