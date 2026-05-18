"""Checks for required project documentation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOCS: dict[str, tuple[str, ...]] = {
    "architecture.md": (
        "routes -> schemas -> services -> repositories -> database",
        "Tenant isolation",
        "Idempotency",
        "Known limitations",
    ),
    "security.md": (
        "not a production identity",
        "API key handling",
        "Tenant isolation",
        "Production-hardening gaps",
    ),
    "api-walkthrough.md": (
        "POST /auth/register",
        "POST /orgs",
        "Idempotency-Key",
        "GET /metrics",
    ),
    "operations.md": (
        "Docker Compose",
        "SAAS_API_",
        "quality gate",
        "Known operational limitations",
    ),
    "runbook.md": (
        "Readiness returns 503",
        "Idempotency conflict",
        "Suspected secret exposure",
        "Authorization: Bearer <access-token>",
    ),
}

REQUIRED_ADRS: dict[str, tuple[str, ...]] = {
    "0001-organisations-as-tenants.md": (
        "Use `organisations` as the tenant root",
        "resource ID from another tenant",
    ),
    "0002-role-based-access-control.md": (
        "Use four explicit organisation roles",
        "workflow may remove or downgrade the last owner",
    ),
    "0003-hashed-passwords-and-api-keys.md": (
        "Hash passwords before persistence",
        "one-time create response",
    ),
    "0004-idempotency-records.md": (
        "Support optional `Idempotency-Key` headers",
        "different body hash",
    ),
    "0005-append-only-audit-events.md": (
        "Use an append-only audit service",
        "There is no public audit update or delete workflow",
    ),
}


def test_required_documentation_files_exist_and_cover_core_topics() -> None:
    """Ticket documentation should exist and mention the required themes."""

    docs_dir = ROOT / "docs"
    for relative_path, required_fragments in REQUIRED_DOCS.items():
        document = (docs_dir / relative_path).read_text(encoding="utf-8")
        normalised_document = document.casefold()
        for fragment in required_fragments:
            assert fragment.casefold() in normalised_document, f"{relative_path}: {fragment}"


def test_required_adrs_exist_and_follow_template() -> None:
    """Architecture decision records should exist and use the agreed template."""

    decisions_dir = ROOT / "docs" / "decisions"
    required_sections = ("## Status", "## Context", "## Decision", "## Consequences")
    for relative_path, required_fragments in REQUIRED_ADRS.items():
        document = (decisions_dir / relative_path).read_text(encoding="utf-8")
        normalised_document = document.casefold()
        for fragment in required_sections + required_fragments:
            assert fragment.casefold() in normalised_document, f"{relative_path}: {fragment}"


def test_documentation_index_and_readme_link_to_topic_docs() -> None:
    """The README and docs index should direct reviewers to the project docs."""

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for relative_path in REQUIRED_DOCS:
        assert f"docs/{relative_path}" in readme
        assert f"({relative_path})" in docs_index
    for relative_path in REQUIRED_ADRS:
        assert f"docs/decisions/{relative_path}" in readme
        assert f"(decisions/{relative_path})" in docs_index
