.DEFAULT_GOAL := help

.PHONY: help validate
help:
	@printf '%s\n' 'Forge bootstrap repository'
	@printf '%s\n' 'make validate  Validate public contracts and scripts.'

validate:
	@./tests/validate-contracts.sh
