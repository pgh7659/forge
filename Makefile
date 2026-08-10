.DEFAULT_GOAL := help

PYTHON ?= .venv/bin/python

.PHONY: help setup test contracts validate package
help:
	@printf '%s\n' 'Forge portable control framework'
	@printf '%s\n' 'make setup      Create .venv and install development dependencies.'
	@printf '%s\n' 'make test       Run Python tests.'
	@printf '%s\n' 'make contracts  Validate public files and secret patterns.'
	@printf '%s\n' 'make validate   Run contracts, tests, and the valid example.'
	@printf '%s\n' 'make package    Build source and wheel distributions.'

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'

test:
	$(PYTHON) -m pytest

contracts:
	./tests/validate-contracts.sh

validate: contracts test
	$(PYTHON) -m forge.cli validate --config examples/environments/minimal.yaml

package:
	$(PYTHON) -m build
