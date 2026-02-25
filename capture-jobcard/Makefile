PYTHON = .venv/bin/python

.PHONY: setup all setup-sa test-auth list clean help

## Setup
setup: .venv ## Create venv + install dependencies
	$(PYTHON) -m pip install -r requirements.txt

.venv:
	python3 -m venv .venv

## Capture
all: ## Capture all saved URLs (email-optimised)
	@TS=$$(date +%Y%m%d_%H%M%S); \
	for name in $$($(PYTHON) -c "import json; print(' '.join(json.load(open('.urls.json')).keys()))"); do \
		echo "=== Capturing $$name ==="; \
		$(PYTHON) main.py --name $$name --timestamp $$TS || echo "  FAILED: $$name (skipping)"; \
	done

## Service Account
setup-sa: ## Show service account setup instructions
	@echo ""
	@echo "  ┌─────────────────────────────────────────────────┐"
	@echo "  │  Google Service Account Setup                   │"
	@echo "  ├─────────────────────────────────────────────────┤"
	@echo "  │  1. Go to console.cloud.google.com              │"
	@echo "  │  2. Create a Service Account                    │"
	@echo "  │  3. Download the JSON key file                  │"
	@echo "  │  4. Save it as .credentials.json here           │"
	@echo "  │  5. Share each Google Sheet with the            │"
	@echo "  │     service account email address               │"
	@echo "  │     (Viewer permission is sufficient)           │"
	@echo "  └─────────────────────────────────────────────────┘"
	@echo ""

test-auth: ## Test service account authentication
	@$(PYTHON) -c "\
	from gsheet import test_auth; \
	ok, name = test_auth(credentials_file='.credentials.json'); \
	print('  Test (' + name + '): \033[32mOK — credentials are valid\033[0m' if ok else '  Test (' + name + '): \033[31mFAILED — check .credentials.json and sheet sharing\033[0m') \
	"

## Management
list: ## List saved URLs
	$(PYTHON) main.py --list

clean: ## Remove all output files
	rm -rf output/

## Help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
