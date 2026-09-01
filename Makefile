SHELL := /bin/sh
API_DIR := apps/api
WEB_FILTER := @companion/web
export PYTHONPATH := $(CURDIR)/apps/api/src

.PHONY: setup lint test test-e2e demo eval dev api web cleanup

setup:
	uv sync --all-packages --extra dev
	pnpm install --frozen-lockfile=false

lint:
	uv run --package companion-ai-api ruff check apps/api
	uv run --package companion-ai-api mypy apps/api/src
	pnpm --filter $(WEB_FILTER) lint
	pnpm --filter $(WEB_FILTER) typecheck

test:
	uv run --package companion-ai-api pytest apps/api/tests -q
	pnpm --filter $(WEB_FILTER) test

test-e2e:
	pnpm --filter $(WEB_FILTER) test:e2e

demo:
	uv run --package companion-ai-api companion demo

eval:
	uv run --package companion-ai-api companion eval

dev:
	@echo "Run 'make api' and 'make web' in separate terminals."

api:
	uv run --package companion-ai-api uvicorn companion.api:app --reload --port 8000

web:
	pnpm --filter $(WEB_FILTER) dev

cleanup:
	uv run --package companion-ai-api companion cleanup
