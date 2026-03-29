.PHONY: docs docs-build docs-fast

docs: ## Serve documentation with live reload
	@PORT=$$(grep -oP 'dev_addr:.*:\K\d+' mkdocs.yml 2>/dev/null || echo 8400); \
	lsof -ti:$$PORT | xargs -r kill 2>/dev/null; \
	echo "Documentation server: http://localhost:$$PORT"; \
	uv run mkdocs serve --dev-addr "localhost:$$PORT"

docs-build: ## Build and validate docs (CI target)
	uv run mkdocs build --strict

docs-fast: ## Serve without API doc generation
	ENABLE_MKDOCSTRINGS=false uv run mkdocs serve
