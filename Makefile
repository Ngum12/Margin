# Thin wrapper over the cross-platform scripts in scripts/. On Windows without make,
# run the python commands directly (see CLAUDE.md).
PYTHON ?= python

.PHONY: install check fix run dev

install:
	cd backend && UV_PYTHON_PREFERENCE=only-managed uv sync --frozen
	cd frontend && npm ci

check:
	$(PYTHON) scripts/check.py

fix:
	$(PYTHON) scripts/check.py --fix

run:
	$(PYTHON) scripts/run.py

dev:
	$(PYTHON) scripts/run.py --dev
