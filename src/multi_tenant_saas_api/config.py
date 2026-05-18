"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import ClassVar, Final

from pydantic import field_validator
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings loaded from the current process environment."""

    return Settings()
