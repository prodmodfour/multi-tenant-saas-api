"""Static tests for repository automation guardrail scripts."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_guardrail(
    script_name: str,
    root: Path,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a guardrail shell wrapper against a fixture repository root."""

    env = os.environ.copy()
    env["GUARDRAIL_ROOT"] = str(root)
    if extra_env is not None:
        env.update(extra_env)

    return subprocess.run(
        ["bash", str(ROOT / "scripts" / script_name)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_guardrail_scripts_are_wired_into_quality_gate_and_ci() -> None:
    """The local quality gate and CI workflow should execute every guardrail."""

    script_names = (
        "check-public-safety.sh",
        "check-architecture-boundaries.sh",
        "check-secret-leakage.sh",
    )
    quality_gate = (ROOT / "scripts/quality-gate.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    for script_name in script_names:
        script = ROOT / "scripts" / script_name
        assert script.exists()
        assert script_name in quality_gate
        assert script_name in workflow


def test_public_safety_guardrail_allows_public_safe_placeholders(tmp_path: Path) -> None:
    """Placeholder config and documentation examples should pass public-safety checks."""

    (tmp_path / "example.env").write_text(
        "SAAS_API_JWT_SECRET=local-placeholder-jwt-secret-not-for-production\n"
        "SAAS_API_DATABASE_URL=postgresql+asyncpg://saas_api:saas_api@localhost:5432/saas_api\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "Use `Authorization: Bearer <token>` in local examples only.\n",
        encoding="utf-8",
    )

    result = run_guardrail("check-public-safety.sh", tmp_path)

    assert result.returncode == 0, result.stderr


def test_public_safety_guardrail_rejects_env_files_and_real_secrets(tmp_path: Path) -> None:
    """The public-safety check should catch committed env files and known token shapes."""

    fake_aws_key = "AKIA" + ("A" * 16)
    (tmp_path / ".env").write_text("SAAS_API_JWT_SECRET=not-a-placeholder\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        f"Do not commit cloud keys such as {fake_aws_key}.\n",
        encoding="utf-8",
    )

    result = run_guardrail("check-public-safety.sh", tmp_path)

    assert result.returncode != 0
    assert ".env-style" in result.stderr
    assert "AWS access key id" in result.stderr


def test_public_safety_guardrail_uses_locally_supplied_forbidden_terms(
    tmp_path: Path,
) -> None:
    """Private/employer term checks should be supplied locally and not committed."""

    term = "ForbiddenCorpLocal"
    forbidden_terms_file = tmp_path.parent / f"{tmp_path.name}-forbidden-terms.txt"
    forbidden_terms_file.write_text(f"{term}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        f"This public portfolio must not mention {term}.\n",
        encoding="utf-8",
    )

    result = run_guardrail(
        "check-public-safety.sh",
        tmp_path,
        {"SAAS_API_FORBIDDEN_TERMS_FILE": str(forbidden_terms_file)},
    )

    assert result.returncode != 0
    assert "locally forbidden private term" in result.stderr


def test_public_safety_guardrail_rejects_raw_bearer_examples(tmp_path: Path) -> None:
    """Sample docs should use placeholder bearer values, not raw-looking tokens."""

    (tmp_path / "README.md").write_text(
        "Authorization: Bearer live-secret-token-value-abcdef\n",
        encoding="utf-8",
    )

    result = run_guardrail("check-public-safety.sh", tmp_path)

    assert result.returncode != 0
    assert "non-placeholder bearer token" in result.stderr


def test_architecture_guardrail_rejects_route_persistence_imports(tmp_path: Path) -> None:
    """Route modules must not import SQLAlchemy or execute persistence calls directly."""

    routes_dir = tmp_path / "src" / "multi_tenant_saas_api" / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "bad.py").write_text(
        "from sqlalchemy import select\n\n"
        "async def bad_route(session):\n"
        "    await session.execute(select(1))\n",
        encoding="utf-8",
    )

    result = run_guardrail("check-architecture-boundaries.sh", tmp_path)

    assert result.returncode != 0
    assert "forbidden persistence module 'sqlalchemy'" in result.stderr
    assert "route calls '.execute()'" in result.stderr


def test_architecture_guardrail_allows_thin_service_routes(tmp_path: Path) -> None:
    """Thin routes that depend on service collaborators should pass."""

    routes_dir = tmp_path / "src" / "multi_tenant_saas_api" / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "good.py").write_text(
        "from multi_tenant_saas_api.dependencies import get_project_api_service\n\n"
        "async def good_route(project_service):\n"
        "    return await project_service.list_projects()\n",
        encoding="utf-8",
    )

    result = run_guardrail("check-architecture-boundaries.sh", tmp_path)

    assert result.returncode == 0, result.stderr


def test_secret_leakage_guardrail_rejects_response_secret_fields(tmp_path: Path) -> None:
    """Public response schemas should not expose password or key hashes."""

    schemas_dir = tmp_path / "src" / "multi_tenant_saas_api" / "schemas"
    schemas_dir.mkdir(parents=True)
    (schemas_dir / "bad.py").write_text(
        "class BadResponse:\n    password_hash: str\n    key_hash: str\n",
        encoding="utf-8",
    )

    result = run_guardrail("check-secret-leakage.sh", tmp_path)

    assert result.returncode != 0
    assert "BadResponse" in result.stderr
    assert "password_hash" in result.stderr
    assert "key_hash" in result.stderr


def test_secret_leakage_guardrail_allows_intentional_auth_and_key_responses(
    tmp_path: Path,
) -> None:
    """The only allowed secret response fields are documented one-time auth/key outputs."""

    schemas_dir = tmp_path / "src" / "multi_tenant_saas_api" / "schemas"
    schemas_dir.mkdir(parents=True)
    (schemas_dir / "allowed.py").write_text(
        "class LoginResponse:\n"
        "    access_token: str\n"
        "    token_type: str\n\n"
        "class APIKeyCreateResponse:\n"
        "    raw_key: str\n",
        encoding="utf-8",
    )

    result = run_guardrail("check-secret-leakage.sh", tmp_path)

    assert result.returncode == 0, result.stderr
