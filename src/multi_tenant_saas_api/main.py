"""ASGI entrypoint for running the API."""

from multi_tenant_saas_api.app import create_app

app = create_app()

__all__ = ["app"]
