"""Static checks for the GitHub Actions CI workflow."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflow_declares_python_uv_and_postgresql_service() -> None:
    """CI should use Python 3.12, uv, and a PostgreSQL service for migrations."""

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "actions/setup-python@v5" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "astral-sh/setup-uv@v5" in workflow
    assert "services:" in workflow
    assert "postgres:" in workflow
    assert "image: postgres:16-alpine" in workflow
    assert "POSTGRES_PASSWORD: local-placeholder-postgres-password" in workflow
    assert "--health-cmd" in workflow
    assert "SAAS_API_DATABASE_URL:" in workflow
    assert "local-placeholder" in workflow


def test_ci_workflow_runs_required_quality_and_migration_steps() -> None:
    """CI should mirror the quality gate and run Alembic against PostgreSQL."""

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    required_fragments = [
        "bash -n",
        "scripts/check-public-safety.sh",
        "scripts/check-architecture-boundaries.sh",
        "scripts/check-secret-leakage.sh",
        "uv sync --locked --all-groups",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy src tests",
        "docker compose config >/dev/null",
        "uv run alembic upgrade head",
        "uv run pytest --cov=multi_tenant_saas_api --cov-report=term-missing",
    ]

    for fragment in required_fragments:
        assert fragment in workflow
