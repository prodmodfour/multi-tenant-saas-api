#!/usr/bin/env python3
"""Repository automation guardrails for public-safe portfolio maintenance."""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pi",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "venv",
    }
)
BINARY_SUFFIXES = frozenset(
    {
        ".db",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".pdf",
        ".png",
        ".pyc",
        ".sqlite",
        ".webp",
    }
)
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private key block",
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    ),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "GitHub token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    ),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Stripe live secret key", re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "JWT-like bearer token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
)
INTERNAL_HOSTNAME_RE = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:corp|internal|intranet|lan)\b",
    re.IGNORECASE,
)
SAMPLE_FILE_PATTERNS = (
    "*.env.example",
    ".github/workflows/*.yaml",
    ".github/workflows/*.yml",
    "README.md",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    "docs/**/*.md",
    "docs/*.md",
    "example.env",
    "observability/**/*.json",
    "observability/**/*.yaml",
    "observability/**/*.yml",
)
ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*['\"]?(?P<value>[^#'\"\n]+)"
)
JSON_ASSIGNMENT_RE = re.compile(r'^\s*"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"\s*:\s*"(?P<value>[^"\n]+)"')
AUTHORIZATION_RE = re.compile(r"\bAuthorization\s*:\s*Bearer\s+(?P<value>[^\s`'\"]+)", re.I)
SECRET_KEY_MARKERS = (
    "authorization",
    "database_uri",
    "database_url",
    "password",
    "private_key",
    "raw_key",
    "secret",
)
TOKEN_KEY_MARKERS = ("api_key", "token")
NON_SECRET_KEY_MARKERS = (
    "expires",
    "issuer",
    "min_length",
    "prefix",
    "timeout",
    "ttl",
    "type",
)
PLACEHOLDER_VALUE_MARKERS = (
    "${",
    "<",
    "changeme",
    "demo",
    "example",
    "localhost",
    "local-placeholder",
    "not-for-production",
    "placeholder",
    "replace-me",
    "saas_api",
)
BANNED_ROUTE_IMPORT_PREFIXES = (
    "multi_tenant_saas_api.database",
    "multi_tenant_saas_api.repositories",
    "sqlalchemy",
)
BANNED_ROUTE_CALL_ATTRIBUTES = frozenset(
    {"commit", "execute", "flush", "refresh", "rollback", "scalar", "scalars"}
)
BANNED_ROUTE_CALL_NAMES = frozenset(
    {
        "create_access_token",
        "generate_raw_key",
        "hash_api_key",
        "hash_key",
        "hash_password",
        "sha256",
        "token_urlsafe",
        "validate_access_token",
        "verify_password",
    }
)
SECRET_RESPONSE_FIELDS = frozenset(
    {
        "api_key_hash",
        "authorization",
        "bearer_token",
        "jwt_secret",
        "key_hash",
        "password",
        "password_hash",
        "raw_api_key",
        "raw_key",
        "refresh_token",
        "secret",
    }
)
SECRET_RESPONSE_FIELD_ALLOWLIST = frozenset(
    {
        ("APIKeyCreateResponse", "raw_key"),
        ("LoginResponse", "access_token"),
    }
)


@dataclass(frozen=True, slots=True)
class Violation:
    """One guardrail violation with optional source location."""

    path: Path
    message: str
    line_number: int | None = None

    def render(self, root: Path) -> str:
        """Return a stable human-readable violation line."""

        try:
            display_path = self.path.relative_to(root)
        except ValueError:
            display_path = self.path
        location = f"{display_path}"
        if self.line_number is not None:
            location = f"{location}:{self.line_number}"
        return f"{location}: {self.message}"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested guardrail."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "check",
        choices=("architecture", "public-safety", "secret-leakage"),
        help="guardrail check to run",
    )
    args = parser.parse_args(argv)
    root = Path(os.environ.get("GUARDRAIL_ROOT", ".")).resolve()

    if args.check == "architecture":
        violations = check_architecture_boundaries(root)
    elif args.check == "public-safety":
        violations = check_public_safety(root)
    else:
        violations = check_secret_leakage(root)

    if violations:
        print(f"{args.check} guardrail failed:", file=sys.stderr)
        for violation in sorted(violations, key=lambda item: item.render(root)):
            print(f"- {violation.render(root)}", file=sys.stderr)
        return 1

    print(f"{args.check} guardrail passed")
    return 0


def check_public_safety(root: Path) -> list[Violation]:
    """Return public-safety and private-term guardrail violations."""

    files = list(iter_repository_files(root))
    forbidden_terms = load_forbidden_terms(root)
    violations: list[Violation] = []

    for path in files:
        rel_path = relative_path(path, root)
        if is_disallowed_env_file(rel_path):
            violations.append(
                Violation(
                    path=path,
                    message="committed .env-style files are not public-safe; use example.env only",
                )
            )

        text = read_text_file(path)
        if text is None:
            continue
        violations.extend(check_real_looking_secret_patterns(path, text))
        violations.extend(check_internal_hostnames(path, text))
        violations.extend(check_forbidden_terms(path, text, forbidden_terms))
        if is_sample_file(rel_path):
            violations.extend(check_sample_secret_values(path, text))

    return violations


def check_architecture_boundaries(root: Path) -> list[Violation]:
    """Return route-layer architecture boundary violations."""

    routes_dir = root / "src" / "multi_tenant_saas_api" / "routes"
    if not routes_dir.exists():
        return []

    violations: list[Violation] = []
    for path in sorted(routes_dir.glob("*.py")):
        text = read_text_file(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            violations.append(
                Violation(
                    path=path,
                    line_number=exc.lineno,
                    message=f"cannot parse route file: {exc.msg}",
                )
            )
            continue
        visitor = RouteBoundaryVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return violations


def check_secret_leakage(root: Path) -> list[Violation]:
    """Return API response schema secret leakage violations."""

    schemas_dir = root / "src" / "multi_tenant_saas_api" / "schemas"
    if not schemas_dir.exists():
        return []

    violations: list[Violation] = []
    for path in sorted(schemas_dir.glob("*.py")):
        text = read_text_file(path)
        if text is None:
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as exc:
            violations.append(
                Violation(
                    path=path,
                    line_number=exc.lineno,
                    message=f"cannot parse schema file: {exc.msg}",
                )
            )
            continue
        visitor = ResponseSecretVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return violations


class RouteBoundaryVisitor(ast.NodeVisitor):
    """AST visitor for route-layer boundary checks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[Violation] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """Reject direct imports of database/repository/SQLAlchemy modules."""

        for alias in node.names:
            if module_has_banned_prefix(alias.name):
                self.violations.append(
                    Violation(
                        path=self.path,
                        line_number=node.lineno,
                        message=f"route imports forbidden persistence module '{alias.name}'",
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """Reject direct from-imports of database/repository/SQLAlchemy modules."""

        module = node.module or ""
        if module_has_banned_prefix(module):
            self.violations.append(
                Violation(
                    path=self.path,
                    line_number=node.lineno,
                    message=f"route imports forbidden persistence module '{module}'",
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Reject obvious SQLAlchemy/session or secret utility calls from routes."""

        if isinstance(node.func, ast.Attribute) and node.func.attr in BANNED_ROUTE_CALL_ATTRIBUTES:
            self.violations.append(
                Violation(
                    path=self.path,
                    line_number=node.lineno,
                    message=(
                        f"route calls '.{node.func.attr}()'; database operations belong in "
                        "repositories/services"
                    ),
                )
            )
        elif isinstance(node.func, ast.Name) and node.func.id in BANNED_ROUTE_CALL_NAMES:
            self.violations.append(
                Violation(
                    path=self.path,
                    line_number=node.lineno,
                    message=(
                        f"route calls '{node.func.id}()'; hashing/token workflows belong "
                        "in services"
                    ),
                )
            )
        self.generic_visit(node)


class ResponseSecretVisitor(ast.NodeVisitor):
    """AST visitor for response schema secret-field checks."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[Violation] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        """Reject secret-looking fields on public response schema classes."""

        if not is_response_schema_class(node.name):
            return

        for field_name, line_number in iter_class_field_names(node):
            if not is_secret_response_field(field_name):
                continue
            if (node.name, field_name) in SECRET_RESPONSE_FIELD_ALLOWLIST:
                continue
            self.violations.append(
                Violation(
                    path=self.path,
                    line_number=line_number,
                    message=(
                        f"response schema '{node.name}' exposes secret-looking field '{field_name}'"
                    ),
                )
            )


def iter_repository_files(root: Path) -> Iterable[Path]:
    """Yield tracked and non-ignored repository files, falling back to a filesystem walk."""

    git_files = git_list_files(root)
    if git_files is not None:
        yield from git_files
        return

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if should_exclude_path(path, root):
            continue
        yield path


def git_list_files(root: Path) -> list[Path] | None:
    """Return tracked and non-ignored git files, or None outside a git checkout."""

    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            check=True,
            capture_output=True,
            text=False,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    paths: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        decoded = raw_path.decode("utf-8", errors="replace")
        path = root / decoded
        if path.is_file() and not should_exclude_path(path, root):
            paths.append(path)
    return sorted(paths)


def should_exclude_path(path: Path, root: Path) -> bool:
    """Return whether a path should be skipped by guardrail scans."""

    rel_path = relative_path(path, root)
    if any(part in EXCLUDED_DIRECTORIES for part in rel_path.parts):
        return True
    return path.suffix.lower() in BINARY_SUFFIXES


def read_text_file(path: Path) -> str | None:
    """Read a likely text file, returning None for binary or undecodable content."""

    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def relative_path(path: Path, root: Path) -> Path:
    """Return path relative to root when possible."""

    try:
        return path.relative_to(root)
    except ValueError:
        return path


def is_disallowed_env_file(rel_path: Path) -> bool:
    """Return whether a repository file is a committed .env-style secret file."""

    name = rel_path.name
    if name == ".env":
        return True
    return name.startswith(".env.") and name != ".env.example"


def check_real_looking_secret_patterns(path: Path, text: str) -> list[Violation]:
    """Return violations for high-confidence real secret patterns."""

    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                violations.append(
                    Violation(
                        path=path,
                        line_number=line_number,
                        message=f"real-looking secret detected ({label})",
                    )
                )
    return violations


def check_internal_hostnames(path: Path, text: str) -> list[Violation]:
    """Return violations for private/internal-looking hostnames."""

    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if INTERNAL_HOSTNAME_RE.search(line):
            violations.append(
                Violation(
                    path=path,
                    line_number=line_number,
                    message="internal-looking hostname detected",
                )
            )
    return violations


def load_forbidden_terms(root: Path) -> tuple[str, ...]:
    """Load locally supplied forbidden private/employer terms."""

    terms_file = os.environ.get("SAAS_API_FORBIDDEN_TERMS_FILE") or os.environ.get(
        "GUARDRAIL_FORBIDDEN_TERMS_FILE"
    )
    if terms_file is None:
        return ()

    path = Path(terms_file).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SystemExit(f"could not read forbidden terms file {path}: {exc}") from exc

    terms: list[str] = []
    for line in lines:
        term = line.strip()
        if not term or term.startswith("#"):
            continue
        terms.append(term.casefold())
    return tuple(terms)


def check_forbidden_terms(path: Path, text: str, forbidden_terms: Sequence[str]) -> list[Violation]:
    """Return violations for locally configured private terms."""

    if not forbidden_terms:
        return []

    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalised_line = line.casefold()
        for term in forbidden_terms:
            if term in normalised_line:
                violations.append(
                    Violation(
                        path=path,
                        line_number=line_number,
                        message="locally forbidden private term detected",
                    )
                )
    return violations


def is_sample_file(rel_path: Path) -> bool:
    """Return whether a file is a sample/config/doc surface worth extra secret checks."""

    candidate = rel_path.as_posix()
    return any(fnmatch.fnmatch(candidate, pattern) for pattern in SAMPLE_FILE_PATTERNS)


def check_sample_secret_values(path: Path, text: str) -> list[Violation]:
    """Return violations for raw token/key/password values in sample files."""

    violations: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        assignment = ASSIGNMENT_RE.match(line) or JSON_ASSIGNMENT_RE.match(line)
        if assignment is not None:
            key = assignment.group("key")
            value = assignment.group("value").strip()
            if is_sensitive_sample_key(key) and not is_placeholder_value(value):
                violations.append(
                    Violation(
                        path=path,
                        line_number=line_number,
                        message=f"sample file assigns non-placeholder sensitive value to '{key}'",
                    )
                )
        authorization = AUTHORIZATION_RE.search(line)
        if authorization is not None:
            value = authorization.group("value").strip()
            if not is_placeholder_value(value):
                violations.append(
                    Violation(
                        path=path,
                        line_number=line_number,
                        message="sample file contains non-placeholder bearer token material",
                    )
                )
    return violations


def is_sensitive_sample_key(key: str) -> bool:
    """Return whether a sample assignment key appears secret-bearing."""

    normalised = key.strip().lower()
    if any(marker in normalised for marker in NON_SECRET_KEY_MARKERS):
        return False
    if any(marker in normalised for marker in SECRET_KEY_MARKERS):
        return True
    return any(marker in normalised for marker in TOKEN_KEY_MARKERS)


def is_placeholder_value(value: str) -> bool:
    """Return whether a value is clearly a public-safe placeholder."""

    normalised = value.strip().strip("'\"").casefold()
    if not normalised:
        return True
    return any(marker in normalised for marker in PLACEHOLDER_VALUE_MARKERS)


def module_has_banned_prefix(module: str) -> bool:
    """Return whether an import module crosses route architecture boundaries."""

    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in BANNED_ROUTE_IMPORT_PREFIXES
    )


def is_response_schema_class(class_name: str) -> bool:
    """Return whether a schema class is part of the public response surface."""

    return class_name.endswith("Response") or class_name.endswith("ListResponse")


def iter_class_field_names(node: ast.ClassDef) -> Iterable[tuple[str, int]]:
    """Yield annotated or assigned field names from a schema class."""

    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            yield statement.target.id, statement.lineno
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    yield target.id, statement.lineno


def is_secret_response_field(field_name: str) -> bool:
    """Return whether a response field name appears to expose secret material."""

    normalised = field_name.strip().lower()
    if normalised in SECRET_RESPONSE_FIELDS:
        return True
    if normalised.endswith("_token") or normalised.endswith("_secret"):
        return True
    return normalised.endswith("_hash") and normalised not in {"request_hash", "body_hash"}


if __name__ == "__main__":
    raise SystemExit(main())
