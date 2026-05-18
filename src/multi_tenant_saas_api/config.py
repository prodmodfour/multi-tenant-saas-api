"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import ClassVar, Final

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from multi_tenant_saas_api import __version__

_VALID_LOG_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
)


class Settings(BaseSettings):
    """Runtime settings for the API.

    Values are read from environment variables prefixed with ``SAAS_API_``.
    Defaults are deliberately local-development friendly and public-safe.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="SAAS_API_",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "multi-tenant-saas-api"
    app_version: str = __version__
    environment: str = "local"
    log_level: str = "INFO"
    docs_enabled: bool = False
    database_url: str = "postgresql+asyncpg://saas_api:saas_api@localhost:5432/saas_api"
    jwt_secret: SecretStr = SecretStr("local-placeholder-jwt-secret-not-for-production")
    jwt_issuer: str = "multi-tenant-saas-api-local"
    access_token_ttl_seconds: int = Field(default=900, ge=1)
    password_min_length: int = Field(default=12, ge=1, le=256)

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, value: str) -> str:
        """Normalise and validate logging levels from the environment."""

        normalised = value.upper()
        if normalised not in _VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(_VALID_LOG_LEVELS))
            msg = f"log_level must be one of: {allowed}"
            raise ValueError(msg)
        return normalised

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        """Ensure the local token signing secret is configured."""

        if value.get_secret_value().strip() == "":
            msg = "jwt_secret must not be empty"
            raise ValueError(msg)
        return value

    @field_validator("jwt_issuer")
    @classmethod
    def validate_jwt_issuer(cls, value: str) -> str:
        """Ensure bearer access tokens have a non-empty issuer."""

        if value.strip() == "":
            msg = "jwt_issuer must not be empty"
            raise ValueError(msg)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings loaded from the current process environment."""

    return Settings()
