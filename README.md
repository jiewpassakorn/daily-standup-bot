# daily-standup-bot

Automated daily stand-up workflow for teams using JIRA and Discord. Captures Google Sheets job cards as images and posts task summaries to Discord via webhook.

## Features

- **Discord Stand-up Bot** — Fetches JIRA issues and posts a formatted summary to Discord (Mon–Fri, scheduled)
- **Job Card Capture** — Exports Google Sheets as PDF, converts to trimmed/merged images
- **Report Generator** — Creates Excel reports from JIRA data with formulas and conditional formatting
- **One Command** — `make daily` runs the full pipeline: capture job cards + post to Discord

## Prerequisites

- Python 3.11+
- A [JIRA Cloud](https://www.atlassian.com/software/jira) account with an API token
- A [Discord webhook](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks) URL
- A [Google Cloud](https://console.cloud.google.com/) service account (for private Google Sheets)

## Quick Start

```bash
# 1. Clone
git clone https://github.com/your-username/daily-standup-bot.git
cd daily-standup-bot

# 2. Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Setup capture-jobcard venv
make -C capture-jobcard setup

# 4. Configure
cp .env.example .env
cp team.json.example team.json
# Edit .env and team.json with your values

# 5. Setup Google Service Account (see below)

# 6. Run
make daily          # Capture job cards + send Discord webhook
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Description | Example |
|----------|-------------|---------|
| `JIRA_BASE_URL` | JIRA Cloud instance URL | `https://yourteam.atlassian.net` |
| `JIRA_EMAIL` | JIRA account email | `you@company.com` |
| `JIRA_API_TOKEN` | [JIRA API token](https://id.atlassian.com/manage-profile/security/api-tokens) | `ATATT3x...` |
| `JIRA_PROJECT_KEY` | JIRA project key | `MYPROJECT` |
| `DISCORD_WEBHOOK_URL` | Discord channel webhook URL | `https://discord.com/api/webhooks/...` |
| `STANDUP_HOUR` | Hour to post (24h format) | `9` |
| `STANDUP_MINUTE` | Minute to post | `0` |
| `TIMEZONE` | Timezone for scheduling | `Asia/Bangkok` |

### Team Configuration

Copy `team.json.example` to `team.json` and add your team members:

```json
[
    {"display": "Alice A.", "jira_name": "alice.smith"},
    {"display": "Bob B.", "jira_name": "bob.jones"}
]
```

- `display` — Short name shown in report columns
- `jira_name` — JIRA assignee name (must match exactly)

## Google Service Account Setup

Required for accessing private Google Sheets.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable **Google Drive API** (APIs & Services > Library)
4. Go to **APIs & Services > Credentials**
5. Click **Create Credentials > Service Account**
6. Download the JSON key file
7. Save it as `capture-jobcard/.credentials.json`
8. **Share each Google Sheet** with the service account email (Viewer permission)

Test your setup:

```bash
make -C capture-jobcard test-auth
```

## Usage

```bash
# Full pipeline: capture + post
make daily

# Capture job cards only
make capture

# Post to Discord only (uses latest captured images)
make webhook

# Run scheduler (posts Mon-Fri at configured time)
python discord_bot.py

# Post once immediately
python discord_bot.py --now
```

### Capture-jobcard Commands

```bash
cd capture-jobcard

make all              # Capture all saved URLs
make test-auth        # Test service account credentials
make list             # List saved Google Sheet URLs
make clean            # Remove output files
make help             # Show all commands

# Save a new Google Sheet URL
python main.py --url "https://docs.google.com/spreadsheets/d/.../edit#gid=0" --save my-sheet

# Capture a specific saved URL
python main.py --name my-sheet
```

## Project Structure

```
daily-standup-bot/
├── discord_bot.py            # Discord stand-up bot (scheduler + webhook)
├── generate_report.py        # Excel report generator
├── Makefile                  # Root orchestration (daily, capture, webhook)
├── requirements.txt          # Python dependencies
├── .env.example              # Configuration template
├── team.json.example         # Team members template
├── capture-jobcard/          # Google Sheets → Image converter
│   ├── main.py               # CLI entry point (typer)
│   ├── gsheet.py             # Google Sheets download + auth
│   ├── converter.py          # PDF → Image conversion
│   ├── Makefile              # Capture commands
│   └── requirements.txt      # Capture-specific dependencies
└── README.md
```

## License

[MIT](LICENSE)
