"""Static checks for the local container runtime configuration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_uses_non_root_runtime_user_and_healthcheck() -> None:
    """The runtime image should not run as root and should expose a liveness check."""

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/healthz" in dockerfile
    assert "multi_tenant_saas_api.main:app" in dockerfile


def test_dockerignore_excludes_local_state_and_secret_files() -> None:
    """The Docker build context should avoid local caches, venvs, and env files."""

    patterns = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert ".env" in patterns
    assert ".env.*" in patterns
    assert ".venv/" in patterns
    assert ".git/" in patterns
    assert ".pytest_cache/" in patterns


def test_compose_stack_declares_required_local_services() -> None:
    """The demo Compose stack should include API, database, and observability services."""

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    for service in ("api", "postgres", "prometheus", "grafana"):
        assert f"  {service}:" in compose

    assert "SAAS_API_DATABASE_URL" in compose
    assert "local-placeholder-postgres-password" in compose
    assert "local-placeholder-jwt-secret-not-for-production" in compose
    assert "alembic upgrade head" in compose
    assert "condition: service_healthy" in compose
