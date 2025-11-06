.PHONY: help venv package docs lint typecheck test install clean

UV ?= uv
PYTHON ?= .venv/bin/python

help:
	@echo "Available targets:"
	@echo "  venv        - Create a local .venv using uv for builds and tooling"
	@echo "  package     - Build distributable artifacts for Codex (wheel + sdist)"
	@echo "  docs        - Build API documentation from source into ./docs"
	@echo "  lint        - Run Ruff lint checks"
	@echo "  typecheck   - Run mypy static type checks"
	@echo "  test        - Run unit tests under ./tests using pytest"
	@echo "  install     - Install the CLI into $$HOME/.local/bin for direct use"
	@echo "  clean       - Remove build artifacts, caches, and the virtual environment"

venv:
	test -d .venv || $(UV) venv .venv
	$(UV) pip install --python .venv --upgrade pip
	$(UV) pip install --python .venv -e .

package: venv
	$(UV) pip install --python .venv build
	$(PYTHON) -m build

docs: venv
	$(UV) pip install --python .venv pdoc
	rm -rf docs
	mkdir -p docs/config
	PYTHONPATH=. .venv/bin/pdoc --docformat google --output-directory docs codex_sub_agent
	cp config/*.toml docs/config/
	rm -rf docs/config/agents
	cp -R config/agents docs/config/

lint: venv
	$(UV) pip install --python .venv ruff
	.venv/bin/ruff check codex_sub_agent tests

typecheck: venv
	$(UV) pip install --python .venv mypy
	.venv/bin/mypy codex_sub_agent

test: venv
	$(UV) pip install --python .venv pytest
	.venv/bin/pytest tests

install:
	python3 -m pip install --user --upgrade .

clean:
	rm -rf .venv build dist *.egg-info
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
