.PHONY: test api ui install

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements-dev.txt

test:
	PYTHONPATH=backend .venv/bin/pytest backend/tests -q

api:
	PYTHONPATH=backend .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

ui:
	npm --prefix frontend run dev
