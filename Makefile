# Development commands for Preprint Radar. Run `make help` (or just `make`) to list them.
#
# Targets are documented with a trailing `## description`; `##@ Title` lines start a
# section of the help.

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Local settings (e.g. PREPRINT_RADAR_CONTACT), see .env.example.
-include .env
export PREPRINT_RADAR_CONTACT

WEB := web
CATEGORIES ?= cs.CV
MAX_HTML ?=
CATEGORY_ARGS := $(foreach category,$(CATEGORIES),--category $(category))
MAX_HTML_ARG := $(if $(MAX_HTML),--max-html $(MAX_HTML))

##@ General

.PHONY: help
help: ## Show this help
	@if [ -t 1 ]; then bold=$$'\033[1m'; cyan=$$'\033[36m'; reset=$$'\033[0m'; fi; \
	printf "Usage: make %s<target>%s [VARIABLE=value ...]\n" "$$cyan" "$$reset"; \
	awk -v bold="$$bold" -v cyan="$$cyan" -v reset="$$reset" ' \
		/^##@/ { printf "\n%s%s%s\n", bold, substr($$0, 5), reset; next } \
		/^[a-zA-Z_-]+:.*## / { split($$0, parts, ":.*## "); printf "  %s%-14s%s %s\n", cyan, parts[1], reset, parts[2] } \
	' $(MAKEFILE_LIST); \
	printf "\n%sVariables%s\n" "$$bold" "$$reset"; \
	printf "  %s%-14s%s %s\n" "$$cyan" "CATEGORIES" "$$reset" "arXiv categories for update targets (default: $(CATEGORIES))"; \
	printf "  %s%-14s%s %s\n" "$$cyan" "MAX_HTML" "$$reset" "maximum HTML pages read per category (default: no limit)"; \
	printf "\nExample: make update CATEGORIES=\"cs.CV cs.LG\" MAX_HTML=50\n"

.PHONY: install
install: $(WEB)/node_modules ## Install Python and web dependencies, and the git hooks
	uv sync
	uv run pre-commit install

$(WEB)/node_modules: $(WEB)/package-lock.json
	cd $(WEB) && npm ci
	@touch $@

##@ Code quality

.PHONY: format
format: $(WEB)/node_modules ## Format and auto-fix Python and web code
	uv run ruff format .
	uv run ruff check --fix .
	cd $(WEB) && npx biome check --write .

.PHONY: quality
quality: $(WEB)/node_modules ## Run every code quality check: formatting, lint, types (no changes)
	@echo "==> Python: formatting (ruff format)"
	@uv run ruff format --check .
	@echo "==> Python: lint (ruff)"
	@uv run ruff check .
	@echo "==> Python: types (ty)"
	@uv run ty check
	@echo "==> Web: formatting and lint (biome)"
	@cd $(WEB) && npm run --silent lint
	@echo "==> Web: types (tsc)"
	@cd $(WEB) && npm run --silent typecheck
	@echo "==> GitHub workflows (actionlint)"
	@uv run actionlint
	@echo "All quality checks passed."

.PHONY: test
test: $(WEB)/node_modules ## Run the offline test suites (Python and web)
	uv run pytest
	cd $(WEB) && npm test

.PHONY: coverage
coverage: ## Run the Python tests with a coverage report
	uv run pytest --cov

.PHONY: test-network
test-network: ## Run smoke tests against the live arXiv (slow)
	uv run pytest -m network

.PHONY: check
check: quality test ## Run quality checks and tests, as CI does

.PHONY: pre-commit
pre-commit: ## Run all git hooks on all files
	uv run pre-commit run --all-files

##@ Data

.PHONY: update
update: ## Add recent papers to data/, with abstracts and affiliations (slow)
	uv run preprint-radar -v update $(CATEGORY_ARGS) $(MAX_HTML_ARG)

.PHONY: update-quick
update-quick: ## Add recent papers to data/ without reading HTML pages (fast)
	uv run preprint-radar -v update $(CATEGORY_ARGS) --max-html 0

##@ Web app

.PHONY: dev
dev: $(WEB)/node_modules ## Start the site with hot reload on http://localhost:5173
	cd $(WEB) && npm run dev

.PHONY: build
build: $(WEB)/node_modules ## Build the site into web/dist, as deployed on GitHub Pages
	cd $(WEB) && npm run build

.PHONY: preview
preview: build ## Build the site and serve the production build locally
	cd $(WEB) && npx vite preview --open

##@ Housekeeping

.PHONY: clean
clean: ## Remove caches and build outputs (keeps data/ and dependencies)
	rm -rf .pytest_cache .ruff_cache .coverage coverage.xml htmlcov exports $(WEB)/dist
	find . \( -path ./.venv -o -path ./$(WEB)/node_modules \) -prune -o -name __pycache__ -type d -exec rm -rf {} +
