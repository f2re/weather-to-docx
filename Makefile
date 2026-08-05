.PHONY: install version-contract development-contract test lint compile js-check check verify agent-check sample api worker offline-bundle clean

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e '.[dev]'

version-contract:
	python scripts/check-version.py

development-contract:
	python scripts/check-development-contract.py

test:
	PYTHONPATH=src pytest

lint:
	ruff check .

compile:
	python -m compileall -q src

js-check:
	node --check src/weather_to_docx/static/app.js
	node --check src/weather_to_docx/static/reliability.js
	node --check src/weather_to_docx/static/compact_report.js
	for script in scripts/*.sh; do bash -n "$$script"; done

check: version-contract development-contract lint test compile js-check

verify:
	weather-to-docx-verify --deep

agent-check: check verify

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
