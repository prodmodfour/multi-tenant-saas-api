"""Request-scoped context helpers."""

import contextvars
import re
import uuid
from typing import Final

REQUEST_ID_HEADER: Final = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH: Final = 128
_REQUEST_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._:-]+$")
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    """Return the request ID bound to the current context, if any."""

    return _request_id.get()


def bind_request_id(request_id: str) -> contextvars.Token[str | None]:
    """Bind a request ID for structured logs emitted while handling a request."""

    return _request_id.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    """Reset the request ID context to its previous value."""

    _request_id.reset(token)


def resolve_request_id(incoming_request_id: str | None) -> str:
    """Return a safe request ID, preserving valid inbound IDs when supplied."""

    if incoming_request_id is not None:
        candidate = incoming_request_id.strip()
        if (
            0 < len(candidate) <= _MAX_REQUEST_ID_LENGTH
            and _REQUEST_ID_PATTERN.fullmatch(candidate) is not None
        ):
            return candidate

    return str(uuid.uuid4())
