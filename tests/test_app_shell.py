from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from multi_tenant_saas_api.app import create_app
from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.request_context import REQUEST_ID_HEADER


def build_client(*, docs_enabled: bool = False) -> TestClient:
    settings = Settings(
        app_name="multi-tenant-saas-api-test",
        environment="test",
        log_level="WARNING",
        docs_enabled=docs_enabled,
    )
    return TestClient(create_app(settings))


def test_health_endpoint_returns_application_status() -> None:
    client = build_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "multi-tenant-saas-api-test",
        "version": "0.1.0",
        "environment": "test",
    }
    assert response.headers[REQUEST_ID_HEADER]


def test_request_id_header_is_propagated() -> None:
    client = build_client()
    request_id = "portfolio-test-request-1"

    response = client.get("/healthz", headers={REQUEST_ID_HEADER: request_id})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == request_id


def test_docs_are_disabled_by_default() -> None:
    client = build_client()

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_can_be_enabled_for_local_exploration() -> None:
    client = build_client(docs_enabled=True)

    docs_response = client.get("/docs")
    openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert openapi_response.status_code == 200
    assert openapi_response.json()["info"]["title"] == "multi-tenant-saas-api-test"


def test_settings_are_loaded_from_saas_api_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SAAS_API_APP_NAME", "Configured API")
    monkeypatch.setenv("SAAS_API_DOCS_ENABLED", "true")
    monkeypatch.setenv("SAAS_API_LOG_LEVEL", "debug")

    settings = Settings()

    assert settings.app_name == "Configured API"
    assert settings.docs_enabled is True
    assert settings.log_level == "DEBUG"
