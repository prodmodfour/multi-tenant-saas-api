"""Authentication utility services for password hashes and bearer tokens.

This module contains framework-agnostic helpers that future route and workflow
services can depend on. It deliberately avoids logging or exposing raw passwords,
password hashes, or bearer token values.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final, Self
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from pwdlib import PasswordHash
from pwdlib import exceptions as pwdlib_exceptions
from pydantic import SecretStr

from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.domain import UserID

DEFAULT_PASSWORD_MIN_LENGTH: Final = 12
DEFAULT_PASSWORD_MAX_LENGTH: Final = 256
JWT_ALGORITHM: Final = "HS256"
_ACCESS_TOKEN_TYPE: Final = "access"


class PasswordPolicyError(ValueError):
    """Raised when a password does not satisfy the local demo password policy."""


@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    """Configurable password policy used before hashing new passwords."""

    min_length: int = DEFAULT_PASSWORD_MIN_LENGTH
    max_length: int = DEFAULT_PASSWORD_MAX_LENGTH

    def __post_init__(self) -> None:
        """Validate policy bounds at construction time."""

        if self.min_length < 1:
            msg = "password min_length must be at least 1"
            raise ValueError(msg)
        if self.max_length < self.min_length:
            msg = "password max_length must be greater than or equal to min_length"
            raise ValueError(msg)

    def validate(self, password: str) -> None:
        """Validate a raw password without returning or logging it."""

        if len(password) < self.min_length:
            msg = f"password must be at least {self.min_length} characters"
            raise PasswordPolicyError(msg)
        if len(password) > self.max_length:
            msg = f"password must be at most {self.max_length} characters"
            raise PasswordPolicyError(msg)
        if password.strip() == "":
            msg = "password must contain at least one non-whitespace character"
            raise PasswordPolicyError(msg)

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build a policy from application settings."""

        return cls(min_length=settings.password_min_length)


class PasswordHashingService:
    """Hash and verify passwords using the current recommended Argon2id hasher."""

    __slots__ = ("_password_hash", "_policy")

    def __init__(
        self,
        *,
        policy: PasswordPolicy | None = None,
        password_hash: PasswordHash | None = None,
    ) -> None:
        """Initialise the service with a policy and pwdlib hash helper."""

        self._policy = policy or PasswordPolicy()
        self._password_hash = password_hash or PasswordHash.recommended()

    @property
    def policy(self) -> PasswordPolicy:
        """Return the configured password policy."""

        return self._policy

    def validate_password(self, password: str) -> None:
        """Validate a password against the configured policy."""

        self._policy.validate(password)

    def hash_password(self, password: str) -> str:
        """Return a password hash suitable for persistence instead of the raw password."""

        self.validate_password(password)
        return self._password_hash.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Return whether a raw password matches a stored password hash.

        Invalid or unrecognised stored hashes are treated as authentication
        failures so callers can use the same safe error behaviour as for a wrong
        password.
        """

        if password_hash == "":
            return False

        try:
            return self._password_hash.verify(password, password_hash)
        except pwdlib_exceptions.UnknownHashError:
            return False

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build a password hashing service from application settings."""

        return cls(policy=PasswordPolicy.from_settings(settings))


class PrincipalType(StrEnum):
    """Supported authenticated principal categories."""

    USER = "user"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Authenticated user principal resolved from a bearer access token."""

    principal_type: PrincipalType
    user_id: UserID

    @classmethod
    def for_user(cls, user_id: UUID | UserID) -> Self:
        """Create a user principal from a user UUID."""

        return cls(principal_type=PrincipalType.USER, user_id=UserID(user_id))


@dataclass(frozen=True, slots=True)
class AccessToken:
    """Raw bearer access token plus non-secret expiry metadata for responses."""

    token: str
    token_type: str
    expires_at: datetime
    expires_in_seconds: int


class AccessTokenError(ValueError):
    """Base class for safe bearer token validation errors."""


class AccessTokenExpiredError(AccessTokenError):
    """Raised when a bearer access token has expired."""


class InvalidAccessTokenError(AccessTokenError):
    """Raised when a bearer access token is malformed or cannot be trusted."""


def _utc_now() -> datetime:
    """Return the current aware UTC timestamp."""

    return datetime.now(UTC)


class AccessTokenService:
    """Create and validate signed bearer access tokens for local demo auth."""

    __slots__ = ("_clock", "_issuer", "_secret", "_ttl_seconds")

    def __init__(
        self,
        *,
        secret: str | SecretStr,
        issuer: str,
        ttl_seconds: int,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """Initialise token signing settings.

        ``secret`` values should come from environment-backed settings. The
        committed defaults are local placeholders only, not production secrets.
        """

        secret_value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret

        if secret_value.strip() == "":
            msg = "access token secret must not be empty"
            raise ValueError(msg)
        if issuer.strip() == "":
            msg = "access token issuer must not be empty"
            raise ValueError(msg)
        if ttl_seconds < 1:
            msg = "access token ttl_seconds must be at least 1"
            raise ValueError(msg)

        self._secret = secret_value
        self._issuer = issuer
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build an access token service from application settings."""

        return cls(
            secret=settings.jwt_secret,
            issuer=settings.jwt_issuer,
            ttl_seconds=settings.access_token_ttl_seconds,
        )

    def create_access_token(self, user_id: UUID | UserID) -> AccessToken:
        """Create a signed bearer access token identifying a user principal."""

        issued_at = self._normalise_datetime(self._clock())
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        payload = {
            "sub": str(user_id),
            "iss": self._issuer,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "token_type": _ACCESS_TOKEN_TYPE,
        }
        token = jwt.encode(payload, self._secret, algorithm=JWT_ALGORITHM)

        return AccessToken(
            token=token,
            token_type="bearer",
            expires_at=expires_at,
            expires_in_seconds=self._ttl_seconds,
        )

    def validate_access_token(self, token: str) -> AuthenticatedPrincipal:
        """Validate a signed bearer access token and return its principal."""

        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[JWT_ALGORITHM],
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "sub", "token_type"]},
            )
        except ExpiredSignatureError as exc:
            msg = "access token has expired"
            raise AccessTokenExpiredError(msg) from exc
        except InvalidTokenError as exc:
            msg = "access token is invalid"
            raise InvalidAccessTokenError(msg) from exc

        if payload.get("token_type") != _ACCESS_TOKEN_TYPE:
            msg = "access token is invalid"
            raise InvalidAccessTokenError(msg)

        subject = payload.get("sub")
        if not isinstance(subject, str):
            msg = "access token is invalid"
            raise InvalidAccessTokenError(msg)

        try:
            user_uuid = UUID(subject)
        except ValueError as exc:
            msg = "access token is invalid"
            raise InvalidAccessTokenError(msg) from exc

        return AuthenticatedPrincipal.for_user(user_uuid)

    @staticmethod
    def _normalise_datetime(value: datetime) -> datetime:
        """Return an aware UTC datetime for token timestamps."""

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = [
    "AccessToken",
    "AccessTokenError",
    "AccessTokenExpiredError",
    "AccessTokenService",
    "AuthenticatedPrincipal",
    "DEFAULT_PASSWORD_MAX_LENGTH",
    "DEFAULT_PASSWORD_MIN_LENGTH",
    "InvalidAccessTokenError",
    "JWT_ALGORITHM",
    "PasswordHashingService",
    "PasswordPolicy",
    "PasswordPolicyError",
    "PrincipalType",
]
