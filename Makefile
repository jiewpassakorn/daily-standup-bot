.PHONY: daily jobcard capture capture-jobcard compress webhook help

daily: capture webhook ## Capture ALL projects + send Discord (includes testing-hangseng)

capture: ## Capture ALL projects (includes testing-hangseng), no Discord
	$(MAKE) -C capture-jobcard all

capture-jobcard: ## Capture job cards only (exclude testing-hangseng), no Discord
	$(MAKE) -C capture-jobcard jobcard

jobcard: capture-jobcard compress webhook ## Capture job cards + compress + send Discord

compress: ## Compress latest job card images (no Discord)
	python3 -c "from discord_bot import find_latest_jobcards, compress_jobcards; files = find_latest_jobcards(); files and compress_jobcards(files, quality=60, max_width=1400)"

webhook: ## Send Discord standup message with job card attachments
	python3 discord_bot.py --now

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
