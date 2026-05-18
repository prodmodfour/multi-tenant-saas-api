"""Static checks for the local smoke/demo script."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke-demo.sh"


def test_smoke_demo_script_is_executable_and_shell_parseable() -> None:
    """The demo script should be runnable from a local checkout."""

    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)

    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_smoke_demo_covers_required_local_workflow_steps() -> None:
    """The script should exercise the ticket's required local API workflow."""

    script = SCRIPT.read_text(encoding="utf-8")
    required_fragments = (
        "Register owner user",
        'POST" "/auth/register',
        "Login owner user",
        'POST" "/auth/login',
        "Create organisation tenant",
        'POST" "/orgs',
        "Register second user",
        "Add second user as an organisation member",
        "/orgs/${organisation_id}/members",
        "Create project",
        "/orgs/${organisation_id}/projects",
        "limit=1&offset=0&status=active&name=Launch",
        "Update project",
        'PATCH" "/orgs/${organisation_id}/projects/${project_id}',
        "Create API key",
        "/orgs/${organisation_id}/api-keys",
        "Use API key on an allowed project endpoint",
        'DELETE" "/orgs/${organisation_id}/api-keys/${api_key_id}',
        "/orgs/${organisation_id}/audit-events?limit=20&offset=0",
        'GET" "/metrics',
    )

    for fragment in required_fragments:
        assert fragment in script, fragment


def test_smoke_demo_is_public_safe_and_does_not_print_secret_material() -> None:
    """The demo should use placeholders and avoid logging captured credentials."""

    script = SCRIPT.read_text(encoding="utf-8")

    assert "example.com" in script
    assert "local-placeholder-demo-password" in script
    assert "set -x" not in script
    assert "redact_response_body" in script
    assert "will not print demo passwords, bearer tokens, or raw API key material" in script
    assert "raw key captured in memory only" in script
    assert "unset raw_api_key" in script


def test_reviewer_docs_link_to_smoke_demo() -> None:
    """Reviewer-facing docs should point to the scripted local demo."""

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    walkthrough = (ROOT / "docs" / "api-walkthrough.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")

    for document in (readme, walkthrough, docs_index, operations):
        assert "scripts/smoke-demo.sh" in document
