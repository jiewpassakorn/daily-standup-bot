.PHONY: daily capture webhook help

daily: capture webhook ## Capture job cards + send Discord webhook

capture: ## Capture all job cards from Google Sheets
	$(MAKE) -C capture-jobcard all

webhook: ## Send Discord standup with job card attachments
	python3 discord_bot.py --now

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
