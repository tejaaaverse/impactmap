# IMPACTMAP development shortcuts

.PHONY: help test test-api test-ui build typecheck dev-api dev-ui sample docker-up docker-down

help:
	@echo "IMPACTMAP targets:"
	@echo "  make test       - backend + frontend tests"
	@echo "  make test-api   - backend pytest suite"
	@echo "  make test-ui    - frontend vitest suite"
	@echo "  make typecheck  - TypeScript type check"
	@echo "  make build      - frontend production build"
	@echo "  make dev-api    - run FastAPI on :8000"
	@echo "  make dev-ui     - run Vite on :5173"
	@echo "  make sample     - create demo Git history if missing"
	@echo "  make docker-up  - docker compose up --build"
	@echo "  make docker-down - docker compose down"

test: test-api test-ui

test-api:
	cd backend && DEBUG=false .venv/bin/python -m pytest -q

test-ui:
	cd frontend && npm test

typecheck:
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

dev-api:
	cd backend && DEBUG=false .venv/bin/python -m uvicorn app.main:app --reload --port 8000

dev-ui:
	cd frontend && npm run dev

sample:
	./scripts/init-sample-repo.sh

docker-up:
	docker compose up --build

docker-down:
	docker compose down
