"""Static checks for local Prometheus and Grafana configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]


def test_prometheus_scrapes_api_metrics_endpoint() -> None:
    """Prometheus should scrape the API metrics endpoint on the Compose network."""

    config = (ROOT / "observability/prometheus/prometheus.yml").read_text(encoding="utf-8")

    assert "job_name: multi-tenant-saas-api" in config
    assert "metrics_path: /metrics" in config
    assert "api:8000" in config
    assert "service: multi-tenant-saas-api" in config
    assert "environment: local" in config


def test_grafana_provisions_prometheus_datasource_and_dashboard_provider() -> None:
    """Grafana should boot with a Prometheus datasource and file dashboard provider."""

    datasource_config = (
        ROOT / "observability/grafana/provisioning/datasources/prometheus.yml"
    ).read_text(encoding="utf-8")
    dashboard_provider_config = (
        ROOT / "observability/grafana/provisioning/dashboards/dashboards.yml"
    ).read_text(encoding="utf-8")

    assert "name: Prometheus" in datasource_config
    assert "uid: prometheus" in datasource_config
    assert "url: http://prometheus:9090" in datasource_config
    assert "isDefault: true" in datasource_config

    assert "name: Multi-Tenant SaaS API" in dashboard_provider_config
    assert "folder: Portfolio SaaS API" in dashboard_provider_config
    assert "path: /var/lib/grafana/dashboards" in dashboard_provider_config


def test_grafana_dashboard_json_references_prometheus_metrics() -> None:
    """The provisioned dashboard should contain panels for the implemented metric families."""

    dashboard = cast(
        dict[str, Any],
        json.loads(
            (ROOT / "observability/grafana/dashboards/saas-api-overview.json").read_text(
                encoding="utf-8"
            )
        ),
    )

    assert dashboard["uid"] == "multi-tenant-saas-api-overview"
    assert dashboard["title"] == "Multi-Tenant SaaS API Overview"

    panels = cast(list[dict[str, Any]], dashboard["panels"])
    panel_titles = {cast(str, panel["title"]) for panel in panels}
    assert {
        "API request rate",
        "P95 request latency",
        "Request rate by route template",
        "Domain workflow counters",
    }.issubset(panel_titles)

    datasources: set[str] = set()
    expressions: set[str] = set()
    for panel in panels:
        panel_datasource = cast(dict[str, Any], panel["datasource"])
        datasources.add(cast(str, panel_datasource["uid"]))
        for target in cast(list[dict[str, Any]], panel.get("targets", [])):
            target_datasource = cast(dict[str, Any], target["datasource"])
            datasources.add(cast(str, target_datasource["uid"]))
            expressions.add(cast(str, target["expr"]))

    assert datasources == {"prometheus"}
    expected_metric_fragments = {
        "saas_api_requests_total",
        "saas_api_request_duration_seconds_bucket",
        "saas_api_auth_attempts_total",
        "saas_api_organisations_created_total",
        "saas_api_projects_created_total",
        "saas_api_api_keys_created_total",
        "saas_api_api_keys_revoked_total",
        "saas_api_audit_events_recorded_total",
        "saas_api_idempotency_replays_total",
        "saas_api_idempotency_conflicts_total",
    }
    for metric_fragment in expected_metric_fragments:
        assert any(metric_fragment in expression for expression in expressions)


def test_compose_mounts_observability_configuration() -> None:
    """Compose should mount local Prometheus and Grafana provisioning files read-only."""

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./observability/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" in compose
    assert "./observability/grafana/provisioning:/etc/grafana/provisioning:ro" in compose
    assert "./observability/grafana/dashboards:/var/lib/grafana/dashboards:ro" in compose
