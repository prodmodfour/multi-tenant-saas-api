from uuid import uuid4

from fastapi.testclient import TestClient

from multi_tenant_saas_api.app import create_app
from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.observability import MetricsService


def make_settings() -> Settings:
    return Settings(environment="test", log_level="WARNING", docs_enabled=False)


def test_metrics_endpoint_exposes_prometheus_text_and_key_metric_names() -> None:
    client = TestClient(create_app(make_settings()))

    health_response = client.get("/healthz")
    metrics_response = client.get("/metrics")

    assert health_response.status_code == 200
    assert metrics_response.status_code == 200
    assert metrics_response.headers["content-type"].startswith("text/plain")
    metrics_text = metrics_response.text
    assert "# HELP saas_api_requests_total" in metrics_text
    assert (
        'saas_api_requests_total{method="GET",path="/healthz",status_code="200"} 1.0'
        in metrics_text
    )
    assert "saas_api_request_duration_seconds_count" in metrics_text
    for metric_name in (
        "saas_api_auth_attempts_total",
        "saas_api_organisations_created_total",
        "saas_api_projects_created_total",
        "saas_api_api_keys_created_total",
        "saas_api_api_keys_revoked_total",
        "saas_api_audit_events_recorded_total",
        "saas_api_idempotency_replays_total",
        "saas_api_idempotency_conflicts_total",
    ):
        assert metric_name in metrics_text


def test_request_metrics_use_route_templates_for_tenant_paths() -> None:
    client = TestClient(create_app(make_settings()))
    organisation_id = uuid4()

    response = client.get(f"/orgs/{organisation_id}")
    metrics_text = client.get("/metrics").text

    assert response.status_code == 401
    assert (
        'saas_api_requests_total{method="GET",path="/orgs/{organisation_id}",status_code="401"} 1.0'
    ) in metrics_text
    assert str(organisation_id) not in metrics_text


def test_metrics_service_records_domain_event_counters() -> None:
    metrics = MetricsService()

    metrics.record_auth_attempt(operation="login", outcome="success")
    metrics.record_auth_attempt(operation="login", outcome="failure")
    metrics.record_organisation_created()
    metrics.record_project_created()
    metrics.record_api_key_created()
    metrics.record_api_key_revoked()
    metrics.record_audit_event(action="project.created")
    metrics.record_idempotency_replay()
    metrics.record_idempotency_conflict()

    metrics_text = metrics.render().decode()

    assert 'saas_api_auth_attempts_total{operation="login",outcome="success"} 1.0' in metrics_text
    assert 'saas_api_auth_attempts_total{operation="login",outcome="failure"} 1.0' in metrics_text
    assert "saas_api_organisations_created_total 1.0" in metrics_text
    assert "saas_api_projects_created_total 1.0" in metrics_text
    assert "saas_api_api_keys_created_total 1.0" in metrics_text
    assert "saas_api_api_keys_revoked_total 1.0" in metrics_text
    assert 'saas_api_audit_events_recorded_total{action="project.created"} 1.0' in metrics_text
    assert "saas_api_idempotency_replays_total 1.0" in metrics_text
    assert "saas_api_idempotency_conflicts_total 1.0" in metrics_text
