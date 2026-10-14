.PHONY: install dev test lint typecheck build check docker replay
install: .venv/.genesis-installed frontend/node_modules/.genesis-installed

.venv/.genesis-installed: backend/pyproject.toml
	python3 -m venv .venv
	.venv/bin/pip install -e 'backend[dev]'
	touch $@

frontend/node_modules/.genesis-installed: frontend/package.json frontend/package-lock.json
	npm --prefix frontend ci
	touch $@

dev: install install-laya
	./scripts/dev.sh

test:
	.venv/bin/python -m pytest backend/tests -q

lint:
	.venv/bin/ruff check backend
	.venv/bin/ruff format --check backend
	npm --prefix frontend run lint

typecheck:
	npm --prefix frontend run typecheck

build:
	npm --prefix frontend run build

check: test lint typecheck build

docker:
	docker compose up --build

replay:
	.venv/bin/python scripts/replay.py $(RUN)

.PHONY: e2e
e2e:
	npm --prefix frontend run test:e2e

.PHONY: install-laya
install-laya: .venv-laya/.genesis-installed

.venv-laya/.genesis-installed: scripts/install-laya.sh
	./scripts/install-laya.sh
