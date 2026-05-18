"""HTTP helpers for idempotency-aware routes."""

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from multi_tenant_saas_api.services import IdempotencyReplay

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_REPLAY_HEADER = "Idempotency-Replayed"


def idempotency_replay_response(replay: IdempotencyReplay) -> JSONResponse:
    """Build an HTTP response from a stored idempotency replay snapshot."""

    return JSONResponse(
        content=dict(replay.response_body),
        status_code=replay.response_status_code,
        headers={IDEMPOTENCY_REPLAY_HEADER: "true"},
    )


def idempotency_conflict_response() -> HTTPException:
    """Build a safe response for an idempotency key/body mismatch."""

    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="idempotency key was already used with a different request body",
    )


__all__ = [
    "IDEMPOTENCY_KEY_HEADER",
    "IDEMPOTENCY_REPLAY_HEADER",
    "idempotency_conflict_response",
    "idempotency_replay_response",
]
