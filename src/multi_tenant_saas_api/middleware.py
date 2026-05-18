"""ASGI middleware installation helpers."""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from multi_tenant_saas_api.request_context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    reset_request_id,
    resolve_request_id,
)

_LOGGER = logging.getLogger(__name__)


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
