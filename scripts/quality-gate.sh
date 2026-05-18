#!/usr/bin/env bash
set -euo pipefail

echo "== shell syntax checks =="
for script in scripts/*.sh; do
  [[ -e "$script" ]] || continue
  bash -n "$script"
done

if [[ -f pyproject.toml ]]; then
  echo "== uv sync =="
  if [[ -f uv.lock ]]; then
    uv sync --locked --all-groups
  else
    uv sync --all-groups
  fi

  echo "== ruff check =="
  uv run ruff check .

  echo "== ruff format check =="
  uv run ruff format --check .

  if [[ -d src ]]; then
    echo "== mypy =="
    uv run mypy src tests
  fi

  if [[ -d tests ]]; then
    echo "== pytest =="
    uv run pytest --cov=multi_tenant_saas_api --cov-report=term-missing
  fi
fi

if [[ -f docker-compose.yml ]]; then
  echo "== docker compose config =="
  docker compose config >/dev/null
fi

if [[ -f scripts/check-public-safety.sh ]]; then
  echo "== public-safety guardrail =="
  bash scripts/check-public-safety.sh
fi

if [[ -f scripts/check-architecture-boundaries.sh ]]; then
  echo "== architecture boundary guardrail =="
  bash scripts/check-architecture-boundaries.sh
fi

if [[ -f scripts/check-secret-leakage.sh ]]; then
  echo "== secret leakage guardrail =="
  bash scripts/check-secret-leakage.sh
fi

echo "== quality gate passed =="
