# Development commands for Preprint Radar. Run `make help` (or just `make`) to list them.
#
# Targets are documented with a trailing `## description`; `##@ Title` lines start a
# section of the help.

.DEFAULT_GOAL := help
SHELL := /bin/bash

# Local settings (e.g. PREPRINT_RADAR_CONTACT), see .env.example. The contact goes to every
# command, the Semantic Scholar key only to those that ask Semantic Scholar.
-include .env
export PREPRINT_RADAR_CONTACT
# Not exported even when the shell holds it, which Make would otherwise pass on everywhere.
unexport SEMANTIC_SCHOLAR_API_KEY
# A value given on make's command line also travels in MAKEFLAGS, to every recipe.
MAKEOVERRIDES := $(filter-out SEMANTIC_SCHOLAR_API_KEY=%,$(MAKEOVERRIDES))
archive citations scholar: export SEMANTIC_SCHOLAR_API_KEY := $(SEMANTIC_SCHOLAR_API_KEY)

WEB := web
# Empty: each command's own default, cs.CV for update, backfill, reextract and archive, and
# every stored category for the others.
CATEGORIES ?=
MAX_HTML ?=
SINCE ?=
UNTIL ?=
CATEGORY_ARGS := $(foreach category,$(CATEGORIES),--category $(category))
MAX_HTML_ARG := $(if $(MAX_HTML),--max-html $(MAX_HTML))
UNTIL_ARG := $(if $(UNTIL),--until $(UNTIL))
# PRUNE deletes day files: only 1 or true turn it on, not PRUNE=false.
ARCHIVE_ARGS := $(if $(DRY_RUN),--dry-run) $(if $(BUDGET),--budget $(BUDGET)) $(if $(filter 1 true,$(PRUNE)),--prune)

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
	printf "  %s%-14s%s %s\n" "$$cyan" "CATEGORIES" "$$reset" "arXiv categories (default: cs.CV for update, backfill, reextract and archive; every stored category for the others)"; \
	printf "  %s%-14s%s %s\n" "$$cyan" "MAX_HTML" "$$reset" "maximum HTML pages downloaded per category (default: 600 for update and backfill, no limit for reextract)"; \
	printf "  %s%-14s%s %s\n" "$$cyan" "SINCE, UNTIL" "$$reset" "first and last day for backfill, YYYY-MM-DD (UNTIL defaults to today)"; \
	printf "  %s%-14s%s %s\n" "$$cyan" "BUDGET" "$$reset" "archive: number of older papers it holds (default: the command's)"; \
	printf "  %s%-14s%s %s\n" "$$cyan" "DRY_RUN=1" "$$reset" "archive: report what would change, write nothing"; \
	printf "  %s%-14s%s %s\n" "$$cyan" "PRUNE=1" "$$reset" "archive: delete the day files older than 12 months"; \
	printf "\nExamples: make update CATEGORIES=\"cs.CV cs.LG\" MAX_HTML=50\n"; \
	printf "          make backfill SINCE=2026-09-01\n"; \
	printf "          make archive DRY_RUN=1 BUDGET=5000\n"

.PHONY: install
install: $(WEB)/node_modules ## Install Python and web dependencies, and the git hooks
	uv sync
	uv run prek install

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
coverage: ## Run the Python tests with a coverage report (opened in the browser on macOS)
	uv run pytest --cov --cov-report html
	@if [ "$$(uname)" = Darwin ]; then open ./htmlcov/index.html; else echo "Report: htmlcov/index.html"; fi

.PHONY: test-e2e
test-e2e: $(WEB)/node_modules ## Smoke-test the built site in Chromium, over web/e2e/data (installs Chromium once)
	cd $(WEB) && npx playwright install chromium && npm run test:e2e

.PHONY: test-network
test-network: ## Run smoke tests against the live arXiv (slow)
	uv run pytest -m network

.PHONY: check
check: quality test ## Run quality checks and tests, as CI does

.PHONY: pre-commit
pre-commit: ## Run all git hooks on all files (with prek)
	uv run prek run --all-files

##@ Data

.PHONY: update
update: ## Add recent papers to data/, with abstracts and affiliations (slow)
	uv run preprint-radar -v update $(CATEGORY_ARGS) $(MAX_HTML_ARG)

.PHONY: update-quick
update-quick: ## Add recent papers to data/ without reading HTML pages (fast)
	uv run preprint-radar -v update $(CATEGORY_ARGS) --max-html 0

.PHONY: backfill
backfill: ## Add past days (SINCE to UNTIL) to data/, with abstracts and affiliations (slow)
	@if [ -z "$(SINCE)" ]; then echo "Usage: make backfill SINCE=YYYY-MM-DD [UNTIL=YYYY-MM-DD]" >&2; exit 2; fi
	uv run preprint-radar -v backfill $(CATEGORY_ARGS) --since $(SINCE) $(UNTIL_ARG) $(MAX_HTML_ARG)

.PHONY: archive
archive: ## Keep the most cited older papers in data/ (first run: about 2 hours)
	uv run preprint-radar -v archive $(CATEGORY_ARGS) $(ARCHIVE_ARGS)

.PHONY: institutions
institutions: ## Name the institutions of stored affiliations through ROR, then the rules (minutes)
	uv run preprint-radar -v institutions $(CATEGORY_ARGS)

.PHONY: affiliations
affiliations: ## Ask OpenAlex for the affiliations of stored papers without an HTML page (seconds)
	uv run preprint-radar -v affiliations $(CATEGORY_ARGS)

.PHONY: institutions-again
institutions-again: ## Name the stored institutions again with today's rules, archive included (offline)
	uv run preprint-radar -v institutions --again $(CATEGORY_ARGS)

.PHONY: reextract
reextract: ## Read again the pages of papers extracted by an older version (cache first; MAX_HTML downloads)
	uv run preprint-radar -v reextract $(CATEGORY_ARGS) $(MAX_HTML_ARG)

.PHONY: reclean
reclean: ## Clean the stored affiliations again after a change to the heuristics (offline)
	uv run preprint-radar -v reclean $(CATEGORY_ARGS)

.PHONY: venues
venues: ## Detect the stored venues again after a change to the detection (offline)
	uv run preprint-radar -v venues $(CATEGORY_ARGS)

.PHONY: citations
citations: ## Fetch the citation counts of stored papers without one (ALL=1: every paper)
	uv run preprint-radar -v citations $(CATEGORY_ARGS) $(if $(ALL),--all)

.PHONY: scholar
scholar: ## Fetch the DOI, published venue and author ids of every stored paper (minutes)
	uv run preprint-radar -v scholar $(CATEGORY_ARGS)

.PHONY: validate
validate: ## Check data/ against its contract (errors fail, heuristic warnings do not)
	@uv run preprint-radar validate

.PHONY: stats
stats: ## Show how much of data/ is enriched, per day and per archive year
	@uv run preprint-radar stats $(CATEGORY_ARGS)

.PHONY: quality-affiliations
quality-affiliations: ## Count signs of wrong affiliations, with examples, stored and from the page cache
	@uv run preprint-radar stats --affiliations --page-cache-dir .cache/front-matter $(CATEGORY_ARGS)

.PHONY: extraction-diff
extraction-diff: ## List the papers today's extraction changes, from the page cache (words lost first)
	@uv run preprint-radar stats --affiliations --page-cache-dir .cache/front-matter --changes $(CATEGORY_ARGS)

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
