"""ASGI middleware installation helpers."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from multi_tenant_saas_api.observability import MetricsRecorder
from multi_tenant_saas_api.request_context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    reset_request_id,
    resolve_request_id,
)

_LOGGER = logging.getLogger(__name__)
_UNMATCHED_ROUTE_LABEL = "unmatched"


def install_metrics_middleware(app: FastAPI, metrics: MetricsRecorder) -> None:
    """Install middleware that records Prometheus HTTP request metrics."""

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = time.perf_counter() - started_at
            metrics.record_http_request(
                method=request.method,
                path=_route_label(request),
                status_code=status_code,
                duration_seconds=duration_seconds,
            )


def install_request_id_middleware(app: FastAPI) -> None:
    """Install middleware that propagates ``X-Request-ID`` values."""

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = bind_request_id(request_id)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            _LOGGER.exception(
                "request failed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            raise
        else:
            duration_ms = (time.perf_counter() - started_at) * 1000
            response.headers[REQUEST_ID_HEADER] = request_id
            _LOGGER.info(
                "request completed",
                extra={
                    "http_method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            return response
        finally:
            reset_request_id(token)


def _route_label(request: Request) -> str:
    """Return a low-cardinality route label for request metrics."""

    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str):
        return route_path

    router_path = _router_path_from_scope(request.scope)
    if router_path is not None:
        return router_path

    return _UNMATCHED_ROUTE_LABEL


def _router_path_from_scope(scope: Mapping[str, Any]) -> str | None:
    """Return a router path from ASGI scope data when available."""

    raw_path = scope.get("path")
    if isinstance(raw_path, str) and raw_path in {"/healthz", "/readyz", "/metrics"}:
        return raw_path
    return None
