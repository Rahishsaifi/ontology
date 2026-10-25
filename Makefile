.PHONY: test api ui install run

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt
	npm --prefix frontend install

test:
	PYTHONPATH=backend .venv/bin/pytest backend/tests -q

api:
	PYTHONPATH=backend .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

ui:
	npm --prefix frontend run dev

run:
	./scripts/run-local.sh
