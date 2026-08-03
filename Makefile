.PHONY: install test lint check sample api worker offline-bundle clean

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e '.[dev]'

test:
	PYTHONPATH=src pytest

lint:
	ruff check src tests

check: lint test

sample:
	PYTHONPATH=src python -m weather_to_docx sample --output var/sample

api:
	PYTHONPATH=src python -m weather_to_docx api --host 127.0.0.1 --port 8080

worker:
	PYTHONPATH=src python -m weather_to_docx worker

offline-bundle:
	bash scripts/build-offline-bundle.sh

clean:
	rm -rf build dist .pytest_cache .ruff_cache var
