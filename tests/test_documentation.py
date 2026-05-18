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


def test_required_documentation_files_exist_and_cover_core_topics() -> None:
    """Ticket documentation should exist and mention the required themes."""

    docs_dir = ROOT / "docs"
    for relative_path, required_fragments in REQUIRED_DOCS.items():
        document = (docs_dir / relative_path).read_text(encoding="utf-8")
        normalised_document = document.casefold()
        for fragment in required_fragments:
            assert fragment.casefold() in normalised_document, f"{relative_path}: {fragment}"


def test_documentation_index_and_readme_link_to_topic_docs() -> None:
    """The README and docs index should direct reviewers to the new docs."""

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for relative_path in REQUIRED_DOCS:
        assert f"docs/{relative_path}" in readme
        assert f"({relative_path})" in docs_index
