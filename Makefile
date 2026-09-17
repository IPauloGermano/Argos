.PHONY: up down build logs test backend-test setup

setup:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r backend/requirements.txt

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

backend-test:
	DATABASE_URL="sqlite:////tmp/hermes_test.db" ./.venv/bin/python -m pytest backend/tests -q

test: backend-test
