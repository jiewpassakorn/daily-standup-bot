"""
Discord Daily Stand-up Bot
Posts Jira task summary to Discord via Webhook.

Usage:
    python discord_bot.py          # Run scheduler (posts Mon-Fri at configured time)
    python discord_bot.py --now    # Post once immediately and exit
"""

import os
import re
import sys
import json
import logging
import uuid
import urllib.parse
import urllib.request
import urllib.error
from base64 import b64encode
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from time import sleep


# ── Load .env file ──────────────────────────────────
def load_dotenv():
    """Load KEY=VALUE pairs from .env file into os.environ."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "")
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Bangkok"))
try:
    STANDUP_HOUR = int(os.getenv("STANDUP_HOUR", "9"))
    STANDUP_MINUTE = int(os.getenv("STANDUP_MINUTE", "0"))
except ValueError as e:
    raise SystemExit(f"Invalid STANDUP_HOUR or STANDUP_MINUTE (must be integers): {e}")
JOBCARD_DIR = Path(os.getenv("JOBCARD_DIR", str(Path(__file__).parent / "capture-jobcard/output")))

JIRA_BROWSE_URL = f"{JIRA_BASE_URL}/browse/"
JIRA_API_SEARCH = f"{JIRA_BASE_URL}/rest/api/3/search/jql"

ACTIVE_STATUSES = ["In Progress", "Open", "On Hold"]
STATUS_EMOJI = {
    "In Progress": "\U0001f7e1",
    "Open": "\u26aa",
    "On Hold": "\U0001f534",
    "Closed": "\U0001f7e2",
    "Resolved": "\U0001f535",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Validation ──────────────────────────────────────
def validate_config():
    required = {
        "JIRA_BASE_URL": JIRA_BASE_URL,
        "JIRA_EMAIL": JIRA_EMAIL,
        "JIRA_API_TOKEN": JIRA_API_TOKEN,
        "JIRA_PROJECT_KEY": JIRA_PROJECT_KEY,
        "DISCORD_WEBHOOK_URL": WEBHOOK_URL,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")
    if not re.match(r"^[A-Z][A-Z0-9_]{1,20}$", JIRA_PROJECT_KEY):
        raise SystemExit(
            f"Invalid JIRA_PROJECT_KEY: must be uppercase alphanumeric, got '{JIRA_PROJECT_KEY}'"
        )


# ── Jira API ────────────────────────────────────────
def fetch_jira_issues() -> list[dict] | None:
    """Fetch all non-dropped issues from Jira (with pagination)."""
    jql = (
        f"project = {JIRA_PROJECT_KEY} "
        "AND status NOT IN (Dropped) "
        "ORDER BY status ASC, assignee ASC"
    )
    credentials = b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }

    all_issues = []
    next_page_token = None

    while True:
        query = {
            "jql": jql,
            "fields": "key,summary,status,assignee,issuetype,priority,duedate",
            "maxResults": 100,
        }
        if next_page_token:
            query["nextPageToken"] = next_page_token

        url = f"{JIRA_API_SEARCH}?{urllib.parse.urlencode(query)}"

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            log.error("Jira API %s: %s", e.code, e.read().decode()[:200])
            return None
        except (urllib.error.URLError, OSError) as e:
            log.error("Jira connection error: %s", e)
            return None

        for item in data.get("issues", []):
            fields = item["fields"]
            all_issues.append(
                {
                    "key": item["key"],
                    "summary": fields.get("summary", ""),
                    "status": fields["status"]["name"] if fields.get("status") else "Unknown",
                    "assignee": (
                        fields["assignee"]["displayName"]
                        if fields.get("assignee")
                        else "Unassigned"
                    ),
                    "issue_type": (
                        fields["issuetype"]["name"] if fields.get("issuetype") else ""
                    ),
                    "priority": fields["priority"]["name"] if fields.get("priority") else "",
                    "due_date": fields.get("duedate"),
                    "url": f"{JIRA_BROWSE_URL}{item['key']}",
                }
            )

        if data.get("isLast", True):
            break
        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    log.info("Fetched %d issues from Jira", len(all_issues))
    return all_issues


# ── Embed builder ───────────────────────────────────
def build_standup_embed(issues: list[dict]) -> dict:
    """Build a Discord webhook embed payload from Jira issues."""
    now = datetime.now(TZ)

    # Count by status
    status_counts: dict[str, int] = {}
    for issue in issues:
        s = issue["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    # Summary line
    total = len(issues)
    summary_parts = [f"**Total: {total}**"]
    for status in ["In Progress", "Open", "On Hold", "Resolved", "Closed"]:
        count = status_counts.get(status, 0)
        emoji = STATUS_EMOJI.get(status, "")
        summary_parts.append(f"{emoji} {status}: {count}")
    summary_line = " | ".join(summary_parts)

    # Active tasks grouped by status
    sections = []
    for status in ACTIVE_STATUSES:
        active = [i for i in issues if i["status"] == status]
        if not active:
            continue
        emoji = STATUS_EMOJI.get(status, "")
        lines = [f"\n**{emoji} {status} ({len(active)})**"]
        for issue in active:
            due = issue["due_date"] or "--"
            lines.append(
                f"> [{issue['key']}]({issue['url']}) — {issue['summary']}\n"
                f"> Assignee: **{issue['assignee']}** | Due: {due}"
            )
        sections.append("\n".join(lines))

    description = summary_line + "\n" + "\n".join(sections)

    # Truncate if needed (Discord limit: 4096)
    if len(description) > 4000:
        description = description[:3950] + "\n\n*...truncated. See Jira for full list.*"

    embed = {
        "title": f"Daily Stand-up — {JIRA_PROJECT_KEY}",
        "description": description,
        "color": 0x2F5496,
        "timestamp": now.isoformat(),
        "footer": {
            "text": f"{JIRA_PROJECT_KEY} | {total} issues | {now.strftime('%A, %d %b %Y')}"
        },
    }
    return embed


def build_error_embed(msg: str) -> dict:
    return {
        "title": "Stand-up Report — Error",
        "description": f"Could not fetch data from Jira.\n\n```{msg}```",
        "color": 0xFF5050,
    }


# ── Job card images ────────────────────────────────
def find_latest_jobcards() -> list[Path]:
    """Find merged job card images from the latest capture run."""
    if not JOBCARD_DIR.is_dir():
        log.info("Job card dir not found: %s", JOBCARD_DIR)
        return []

    timestamps = sorted(
        (d for d in JOBCARD_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")),
        reverse=True,
    )
    if not timestamps:
        return []

    latest = timestamps[0]
    files = sorted(latest.glob("*/*_merged.jpg"))
    log.info("Found %d job card(s) in %s", len(files), latest.name)
    return files


# ── Discord Webhook ─────────────────────────────────
def send_webhook(embed: dict, files: list[Path] | None = None):
    """Send an embed to Discord via webhook, optionally with file attachments."""
    if not files:
        payload = json.dumps({"embeds": [embed]}).encode()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "StandupBot/1.0",
        }
        try:
            req = urllib.request.Request(WEBHOOK_URL, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                log.info("Webhook sent (status %s)", resp.status)
        except urllib.error.HTTPError as e:
            log.error("Webhook error %s: %s", e.code, e.read().decode()[:200])
        except (urllib.error.URLError, OSError) as e:
            log.error("Webhook connection error: %s", e)
        return

    # Multipart form-data for file attachments
    boundary = uuid.uuid4().hex
    body = b""

    # payload_json part
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="payload_json"\r\n'
    body += b"Content-Type: application/json\r\n\r\n"
    body += json.dumps({"embeds": [embed]}).encode()
    body += b"\r\n"

    # file parts
    for i, filepath in enumerate(files):
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="files[{i}]"; filename="{filepath.name}"\r\n'.encode()
        body += b"Content-Type: image/jpeg\r\n\r\n"
        body += filepath.read_bytes()
        body += b"\r\n"

    body += f"--{boundary}--\r\n".encode()

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "StandupBot/1.0",
    }

    try:
        req = urllib.request.Request(WEBHOOK_URL, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            log.info("Webhook sent with %d file(s) (status %s)", len(files), resp.status)
    except urllib.error.HTTPError as e:
        log.error("Webhook error %s: %s", e.code, e.read().decode()[:200])
    except (urllib.error.URLError, OSError) as e:
        log.error("Webhook connection error: %s", e)


# ── Post standup ────────────────────────────────────
def post_standup():
    """Fetch Jira data and post to Discord with job card attachments."""
    issues = fetch_jira_issues()
    if issues is None:
        send_webhook(build_error_embed("Jira API request failed"))
        return

    embed = build_standup_embed(issues)
    jobcards = find_latest_jobcards()
    send_webhook(embed, files=jobcards or None)
    log.info("Stand-up posted successfully")


# ── Scheduler ───────────────────────────────────────
def run_scheduler():
    """Run daily scheduler - posts Mon-Fri at configured time."""
    log.info(
        "Scheduler started. Will post Mon-Fri at %02d:%02d (%s)",
        STANDUP_HOUR,
        STANDUP_MINUTE,
        TZ,
    )

    while True:
        now = datetime.now(TZ)
        # Check if it's the right time (within the same minute)
        if (
            now.weekday() < 5
            and now.hour == STANDUP_HOUR
            and now.minute == STANDUP_MINUTE
        ):
            post_standup()
            # Sleep 61 seconds to avoid posting twice in the same minute
            sleep(61)
        else:
            sleep(30)


# ── Entry point ─────────────────────────────────────
if __name__ == "__main__":
    validate_config()

    if "--now" in sys.argv:
        log.info("Running stand-up now (manual trigger)")
        post_standup()
    else:
        run_scheduler()
