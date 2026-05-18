.PHONY: install lint format format-check typecheck test quality

UV ?= uv

install:
	$(UV) sync --all-groups

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .

format-check:
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy src tests

test:
	$(UV) run pytest --cov=multi_tenant_saas_api --cov-report=term-missing

quality:
	scripts/quality-gate.sh
