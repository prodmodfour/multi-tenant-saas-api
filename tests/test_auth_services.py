from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pydantic import SecretStr
from pytest import raises

from multi_tenant_saas_api.config import Settings
from multi_tenant_saas_api.domain import UserID
from multi_tenant_saas_api.services import (
    AccessTokenExpiredError,
    AccessTokenService,
    AuthenticatedPrincipal,
    InvalidAccessTokenError,
    PasswordHashingService,
    PasswordPolicy,
    PasswordPolicyError,
    PrincipalType,
)
from multi_tenant_saas_api.services.auth import JWT_ALGORITHM

USER_UUID = UUID("00000000-0000-4000-8000-000000000501")
USER_ID = UserID(USER_UUID)
ISSUER = "multi-tenant-saas-api-test"
JWT_SECRET = "test-placeholder-jwt-secret-not-for-production-0001"
RAW_PASSWORD = "local-demo-password-123"


def test_password_hashing_service_hashes_and_verifies_passwords() -> None:
    service = PasswordHashingService()

    password_hash = service.hash_password(RAW_PASSWORD)

    assert password_hash != RAW_PASSWORD
    assert RAW_PASSWORD not in password_hash
    assert len(password_hash) <= 255
    assert service.verify_password(RAW_PASSWORD, password_hash)
    assert not service.verify_password("wrong-local-demo-password", password_hash)
    assert not service.verify_password(RAW_PASSWORD, "not-a-valid-password-hash")


def test_password_policy_rejects_invalid_passwords_without_exposing_values() -> None:
    policy = PasswordPolicy(min_length=12, max_length=32)

    policy.validate(RAW_PASSWORD)

    with raises(PasswordPolicyError, match="at least 12 characters"):
        policy.validate("short")

    with raises(PasswordPolicyError, match="at most 32 characters"):
        policy.validate("x" * 33)

    with raises(PasswordPolicyError, match="non-whitespace"):
        policy.validate(" " * 12)

    with raises(ValueError):
        PasswordPolicy(min_length=0)

    with raises(ValueError):
        PasswordPolicy(min_length=12, max_length=8)


def test_password_hashing_service_enforces_configured_policy() -> None:
    service = PasswordHashingService(policy=PasswordPolicy(min_length=16))

    with raises(PasswordPolicyError):
        service.hash_password("twelve-chars")

    password_hash = service.hash_password("sixteen-characters")

    assert service.verify_password("sixteen-characters", password_hash)


def test_access_token_service_creates_and_validates_user_principal() -> None:
    issued_at = datetime.now(UTC).replace(microsecond=0)
    service = AccessTokenService(
        secret=JWT_SECRET,
        issuer=ISSUER,
        ttl_seconds=900,
        clock=lambda: issued_at,
    )

    access_token = service.create_access_token(USER_ID)
    principal = service.validate_access_token(access_token.token)

    assert access_token.token
    assert access_token.token_type == "bearer"
    assert access_token.expires_at == issued_at + timedelta(seconds=900)
    assert access_token.expires_in_seconds == 900
    assert principal == AuthenticatedPrincipal.for_user(USER_UUID)
    assert principal.principal_type is PrincipalType.USER
    assert principal.user_id == USER_ID


def test_access_token_validation_rejects_expired_tokens() -> None:
    service = AccessTokenService(secret=JWT_SECRET, issuer=ISSUER, ttl_seconds=900)
    now = datetime.now(UTC)
    expired_token = jwt.encode(
        {
            "sub": str(USER_UUID),
            "iss": ISSUER,
            "iat": int((now - timedelta(minutes=30)).timestamp()),
            "exp": int((now - timedelta(minutes=15)).timestamp()),
            "token_type": "access",
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    with raises(AccessTokenExpiredError, match="expired"):
        service.validate_access_token(expired_token)


def test_access_token_validation_rejects_invalid_tokens() -> None:
    service = AccessTokenService(secret=JWT_SECRET, issuer=ISSUER, ttl_seconds=900)
    now = datetime.now(UTC)
    payload = {
        "sub": str(USER_UUID),
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        "token_type": "access",
    }

    signed_with_wrong_secret = jwt.encode(
        payload,
        "different-placeholder-jwt-secret-not-for-production",
        algorithm=JWT_ALGORITHM,
    )
    with raises(InvalidAccessTokenError, match="invalid"):
        service.validate_access_token(signed_with_wrong_secret)

    malformed_subject = jwt.encode(
        {**payload, "sub": "not-a-uuid"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    with raises(InvalidAccessTokenError, match="invalid"):
        service.validate_access_token(malformed_subject)

    wrong_token_type = jwt.encode(
        {**payload, "token_type": "refresh"},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    with raises(InvalidAccessTokenError, match="invalid"):
        service.validate_access_token(wrong_token_type)


def test_auth_services_build_from_settings_without_revealing_secret_repr() -> None:
    settings = Settings(
        jwt_secret=SecretStr(JWT_SECRET),
        jwt_issuer=ISSUER,
        access_token_ttl_seconds=60,
        password_min_length=16,
    )

    password_service = PasswordHashingService.from_settings(settings)
    token_service = AccessTokenService.from_settings(settings)

    with raises(PasswordPolicyError):
        password_service.hash_password("too-short")

    access_token = token_service.create_access_token(USER_ID)

    assert token_service.validate_access_token(access_token.token).user_id == USER_ID
    assert settings.jwt_secret.get_secret_value() == JWT_SECRET
    assert JWT_SECRET not in repr(settings)
