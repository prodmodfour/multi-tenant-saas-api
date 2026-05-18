"""Prometheus metrics instrumentation.

The application owns one metrics service per FastAPI app instance. Business
services receive a small recorder protocol so they can record domain events
without importing HTTP framework details, and tests can use a no-op recorder when
metrics are not relevant.
"""

from __future__ import annotations

from typing import Protocol

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)


class MetricsRecorder(Protocol):
    """Small interface used by services to record metrics without HTTP coupling."""

    def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one completed HTTP request."""

    def record_auth_attempt(self, *, operation: str, outcome: str) -> None:
        """Record one authentication attempt outcome."""

    def record_organisation_created(self) -> None:
        """Record one successfully created organisation tenant."""

    def record_project_created(self) -> None:
        """Record one successfully created project."""

    def record_api_key_created(self) -> None:
        """Record one successfully created API key."""

    def record_api_key_revoked(self) -> None:
        """Record one successfully revoked API key."""

    def record_audit_event(self, *, action: str) -> None:
        """Record one audit event write by action."""

    def record_idempotency_replay(self) -> None:
        """Record one idempotent replay response."""

    def record_idempotency_conflict(self) -> None:
        """Record one idempotency key/body conflict."""


class NoOpMetricsRecorder:
    """Metrics recorder used where instrumentation is intentionally absent."""

    __slots__ = ()

    def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Ignore HTTP request metrics."""

    def record_auth_attempt(self, *, operation: str, outcome: str) -> None:
        """Ignore authentication attempt metrics."""

    def record_organisation_created(self) -> None:
        """Ignore organisation creation metrics."""

    def record_project_created(self) -> None:
        """Ignore project creation metrics."""

    def record_api_key_created(self) -> None:
        """Ignore API key creation metrics."""

    def record_api_key_revoked(self) -> None:
        """Ignore API key revocation metrics."""

    def record_audit_event(self, *, action: str) -> None:
        """Ignore audit event metrics."""

    def record_idempotency_replay(self) -> None:
        """Ignore idempotency replay metrics."""

    def record_idempotency_conflict(self) -> None:
        """Ignore idempotency conflict metrics."""


class MetricsService:
    """Prometheus-backed metrics recorder and exposition service."""

    __slots__ = (
        "_api_key_creations",
        "_api_key_revocations",
        "_api_request_duration",
        "_api_requests",
        "_audit_events",
        "_auth_attempts",
        "_idempotency_conflicts",
        "_idempotency_replays",
        "_organisation_creations",
        "_project_creations",
        "_registry",
    )

    content_type = CONTENT_TYPE_LATEST

    def __init__(self, *, registry: CollectorRegistry | None = None) -> None:
        """Initialise all collectors in an app-local registry."""

        self._registry = registry or CollectorRegistry(auto_describe=True)
        self._api_requests = Counter(
            "saas_api_requests_total",
            "Total HTTP requests served by the API.",
            ("method", "path", "status_code"),
            registry=self._registry,
        )
        self._api_request_duration = Histogram(
            "saas_api_request_duration_seconds",
            "HTTP request duration in seconds.",
            ("method", "path", "status_code"),
            registry=self._registry,
        )
        self._auth_attempts = Counter(
            "saas_api_auth_attempts_total",
            "Authentication attempts by operation and outcome.",
            ("operation", "outcome"),
            registry=self._registry,
        )
        self._organisation_creations = Counter(
            "saas_api_organisations_created_total",
            "Organisations successfully created.",
            registry=self._registry,
        )
        self._project_creations = Counter(
            "saas_api_projects_created_total",
            "Projects successfully created.",
            registry=self._registry,
        )
        self._api_key_creations = Counter(
            "saas_api_api_keys_created_total",
            "Organisation API keys successfully created.",
            registry=self._registry,
        )
        self._api_key_revocations = Counter(
            "saas_api_api_keys_revoked_total",
            "Organisation API keys successfully revoked.",
            registry=self._registry,
        )
        self._audit_events = Counter(
            "saas_api_audit_events_recorded_total",
            "Audit events accepted by the audit service.",
            ("action",),
            registry=self._registry,
        )
        self._idempotency_replays = Counter(
            "saas_api_idempotency_replays_total",
            "Idempotent requests served from a stored response snapshot.",
            registry=self._registry,
        )
        self._idempotency_conflicts = Counter(
            "saas_api_idempotency_conflicts_total",
            "Idempotency keys rejected because the request body changed.",
            registry=self._registry,
        )

    def render(self) -> bytes:
        """Return Prometheus text exposition for this app's metrics registry."""

        return generate_latest(self._registry)

    def record_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one completed HTTP request."""

        labels = {
            "method": method.upper(),
            "path": path,
            "status_code": str(status_code),
        }
        self._api_requests.labels(**labels).inc()
        self._api_request_duration.labels(**labels).observe(duration_seconds)

    def record_auth_attempt(self, *, operation: str, outcome: str) -> None:
        """Record one authentication attempt outcome."""

        self._auth_attempts.labels(operation=operation, outcome=outcome).inc()

    def record_organisation_created(self) -> None:
        """Record one successfully created organisation tenant."""

        self._organisation_creations.inc()

    def record_project_created(self) -> None:
        """Record one successfully created project."""

        self._project_creations.inc()

    def record_api_key_created(self) -> None:
        """Record one successfully created API key."""

        self._api_key_creations.inc()

    def record_api_key_revoked(self) -> None:
        """Record one successfully revoked API key."""

        self._api_key_revocations.inc()

    def record_audit_event(self, *, action: str) -> None:
        """Record one audit event write by action."""

        self._audit_events.labels(action=action).inc()

    def record_idempotency_replay(self) -> None:
        """Record one idempotent replay response."""

        self._idempotency_replays.inc()

    def record_idempotency_conflict(self) -> None:
        """Record one idempotency key/body conflict."""

        self._idempotency_conflicts.inc()


__all__ = ["MetricsRecorder", "MetricsService", "NoOpMetricsRecorder"]
