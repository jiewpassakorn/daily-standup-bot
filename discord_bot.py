"""
Discord Daily Stand-up Bot
Posts Jira task summary to Discord via Webhook.

Usage:
    python discord_bot.py          # Run scheduler (posts Mon-Fri at configured time)
    python discord_bot.py --now    # Post once immediately and exit
"""

import os
import random
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
WEBHOOK_URLS = [
    u.strip() for u in os.getenv("DISCORD_WEBHOOK_URL", "").split(",") if u.strip()
]
BOT_USERNAME = os.getenv("BOT_USERNAME", "\u0e1a\u0e2d\u0e17\u0e1a\u0e49\u0e32\u0e1e\u0e25\u0e31\u0e07")
BOT_AVATAR_URL = os.getenv("BOT_AVATAR_URL", "")
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
STATUS_COLOR = {
    "In Progress": 0xEAB308,
    "Open": 0x6B7280,
    "On Hold": 0xEF4444,
}
SUMMARY_COLOR = 0x5865F2
GREETINGS = {
    0: [  # Monday
        "จันทร์แล้วครับท่านสมาชิก ลุกขึ้นมา deploy กัน 🚀",
        "Monday again! ใครยังไม่ตื่นให้ coffee เป็น dependency injection 💉☕",
        "สัปดาห์ใหม่ bug ใหม่ มาจัดการกันเถอะ 🐛",
        "วันจันทร์ = git pull แล้วช็อค edition 😱",
        "ตื่นเถอะครับ production ไม่รอใคร 🔔",
        "Happy Monday! อย่าลืม pull ก่อน push ชีวิตนะ 🙏",
        "จันทร์นี้ขอให้ build pass ทุกคนครับ 🏗️",
        "เปิดคอมมาเจอ Jira ท่วม แต่ใจยังสู้! 🫡",
        "Monday motivation: ยัง deploy ไม่พัง ก็ถือว่าชนะแล้ว 🏆",
        "สวัสดีวันจันทร์! ใครัง standup อยู่ยกมือขึ้น 🙋",
    ],
    1: [  # Tuesday
        "อังคารแล้ว momentum ยังอยู่มั้ย หรือ burned out แล้ว 🔥",
        "Tuesday! วันนี้ขอให้ merge โดยไม่มี conflict นะ 🤞",
        "สวัสดีวันอังคาร! ใครยังค้าง PR รีบ review หน่อยนะ 👀",
        "วันอังคาร = วัน debug สิ่งที่วันจันทร์ทำพัง 🔧",
        "Happy Tuesday! code วันนี้อย่าให้ future me ด่า 🙈",
        "อังคารนี้ลุยกันต่อ! ถ้า CI เขียว ก็ไปต่อได้ 🟢",
        "Tuesday energy! กาแฟแก้วที่ 3 ยังไม่ถึงมั้ย? ☕☕☕",
        "วันอังคาร sprint ยัง on track อยู่มั้ยทุกคน? 📊",
        "สวัสดีอังคาร! อย่า push to main ตอนง่วงนะ 😴",
        "Tuesday grind! วันนี้ปิด ticket ได้สักตัวมั้ย 🎫",
    ],
    2: [  # Wednesday
        "ครึ่งทางแล้ว! ใครยังไม่เริ่ม sprint task เริ่มได้แล้วนะ 🐪",
        "Hump Day! ข้ามเขาลูกนี้ไปด้วยกัน 🏔️",
        "วันพุธ ถ้า Jira board ยังแดง ก็ถือว่าปกติ 🟥",
        "Wednesday! ครึ่งสัปดาห์แล้ว ใครยัง blocked บอกในนี้ 🚧",
        "กลางสัปดาห์แล้ว! สู้ๆ อีกนิด Friday รอเราอยู่ 🏁",
        "Happy Hump Day! feature freeze ใกล้แล้วนะ อย่านิ่งนาน 🥶",
        "พุธแล้ว! deploy ไป staging ได้รึยัง? 📦",
        "Midweek check! ใครต้องการ help ยกมือเลย 🤚",
        "สวัสดีวันพุธ! วันนี้ขอให้ tests ผ่านทุกคน 🧪",
        "Wednesday vibes: เขียน code ไม่ยาก ยากตรง requirement เปลี่ยน 📝",
    ],
    3: [  # Thursday
        "พฤหัสแล้ว! deploy วันศุกร์ใครกล้ายกมือ 🙋‍♂️💀",
        "Almost Friday! ปิดงานเถอะ อย่าทิ้งไว้ให้ศุกร์ 📋",
        "Thursday! พรุ่งนี้ศุกร์แล้ว ใครจะ deploy ขอให้คิดดีๆ 🤔",
        "เหลืออีกวันเดียว! สปรินท์นี้ปิดกันได้มั้ย 🏃‍♂️",
        "วันพฤหัส aka วัน code review marathon 👓",
        "Happy Thursday! ทำเสร็จวันนี้ พรุ่งนี้ chill ได้ 😎",
        "Thursday vibes: merge วันนี้ หรือจะเป็น tech debt ตลอดไป 💸",
        "สวัสดีวันพฤหัส! QA กำลังมา ใครยังมี bug รีบแก้ 🕵️",
        "พฤหัสนี้ขอให้ zero bugs ใน production นะ 🙏",
        "Almost there! อย่าเพิ่ง refactor ตอนนี้นะ ขอร้อง 😂",
    ],
    4: [  # Friday
        "TGIF! ใครจะ deploy วันศุกร์ขอให้โชคดี 🍀",
        "ศุกร์แล้ว! freeze code แล้วไป freeze เบียร์กัน 🍺",
        "Happy Friday! วันนี้ read-only Friday นะ อย่า push อะไร 🔒",
        "Friday! ถ้า production ยังไม่ล่ม ถือว่า sprint สำเร็จ 🎉",
        "สุดสัปดาห์แล้ว! ปิด laptop แล้วเปิดชีวิตกัน 🌴",
        "TGIF! ใครมี PR ค้างอยู่ merge ซะก่อน weekend 🏖️",
        "Friday vibes: อย่า deploy แล้วปิดเครื่องหนี ขอร้อง 🏃💨",
        "วันศุกร์แล้ว! ขอให้ on-call สงบสุข ไม่มี alert 📟",
        "Happy Friday! อาทิตย์หน้าค่อย refactor ได้ วันนี้พักก่อน 😴",
        "POETS Day! Push Off Early, Tomorrow's Saturday 🎶",
    ],
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
    }
    missing = [k for k, v in required.items() if not v]
    if not WEBHOOK_URLS:
        missing.append("DISCORD_WEBHOOK_URL")
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


# ── Helpers ─────────────────────────────────────────
def _greeting(weekday: int) -> str:
    """Return a random greeting for the given weekday (0=Mon … 4=Fri)."""
    candidates = GREETINGS.get(weekday, [])
    return random.choice(candidates) if candidates else ""


def _truncate(text: str, max_len: int = 80) -> str:
    """Truncate text to *max_len* characters, adding '...' if trimmed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "\u2026"


def _fmt_due(due_str: str | None) -> str:
    """Format a due date string compactly (e.g. '28 Feb')."""
    if not due_str:
        return ""
    try:
        return datetime.strptime(due_str, "%Y-%m-%d").strftime("%d %b")
    except ValueError:
        return due_str


def _embed_chars(embed: dict) -> int:
    """Count characters that Discord counts toward the 6 000-char limit."""
    n = 0
    for key in ("title", "description"):
        n += len(embed.get(key, ""))
    if "author" in embed:
        n += len(embed["author"].get("name", ""))
    if "footer" in embed:
        n += len(embed["footer"].get("text", ""))
    for field in embed.get("fields", []):
        n += len(field.get("name", ""))
        n += len(field.get("value", ""))
    return n


# ── Embed builder ───────────────────────────────────
def build_standup_embeds(issues: list[dict]) -> list[dict]:
    """Build modern multi-embed Discord payload from Jira issues."""
    now = datetime.now(TZ)

    # Count by status
    status_counts: dict[str, int] = {}
    for issue in issues:
        s = issue["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    total = len(issues)
    active_count = sum(1 for i in issues if i["status"] in ACTIVE_STATUSES)

    # ── Summary embed ──────────────────────────────
    fields = []
    for status in ["In Progress", "Open", "On Hold", "Resolved", "Closed"]:
        count = status_counts.get(status, 0)
        if count == 0:
            continue
        emoji = STATUS_EMOJI.get(status, "")
        fields.append({"name": f"{emoji} {status}", "value": f"**{count}**", "inline": True})

    summary_embed = {
        "author": {"name": "\U0001f4ca Daily Stand-up Report"},
        "title": f"{JIRA_PROJECT_KEY} \u2014 {now.strftime('%A, %d %b %Y')}",
        "description": f"{_greeting(now.weekday())}\n\n> Tracking **{total}** issues \u00b7 **{active_count}** active",
        "fields": fields,
        "color": SUMMARY_COLOR,
    }

    embeds: list[dict] = [summary_embed]

    # ── Status-group embeds ────────────────────────
    for status in ACTIVE_STATUSES:
        group = [i for i in issues if i["status"] == status]
        if not group:
            continue

        emoji = STATUS_EMOJI.get(status, "")
        lines = []
        for issue in group:
            due = _fmt_due(issue["due_date"])
            meta_parts = [issue["assignee"]]
            if due:
                meta_parts.append(due)
            lines.append(
                f"**[{issue['key']}]({issue['url']})** \u2014 {_truncate(issue['summary'])}\n"
                f"*{' \u00b7 '.join(meta_parts)}*"
            )

        desc = "\n\n".join(lines)
        if len(desc) > 4000:
            desc = desc[:3950] + "\n\n*\u2026truncated \u2014 see Jira for full list*"

        embeds.append(
            {
                "title": f"{emoji} {status} \u2014 {len(group)} issue{'s' if len(group) != 1 else ''}",
                "description": desc,
                "color": STATUS_COLOR.get(status, SUMMARY_COLOR),
            }
        )

    # Footer on the last embed
    embeds[-1]["footer"] = {
        "text": f"{BOT_USERNAME}  \u00b7  {JIRA_PROJECT_KEY}  \u00b7  {now.strftime('%H:%M %Z')}"
    }
    embeds[-1]["timestamp"] = now.isoformat()

    # ── Guard Discord's 6 000-char limit ───────────
    total_chars = sum(_embed_chars(e) for e in embeds)
    while total_chars > 5900 and len(embeds) > 1:
        last_group = embeds[-1]
        desc = last_group.get("description", "")
        excess = total_chars - 5900
        if len(desc) > excess + 60:
            last_group["description"] = desc[: len(desc) - excess - 50] + "\n\n*\u2026truncated*"
        else:
            last_group["description"] = "*Too many issues to display \u2014 see Jira board.*"
        total_chars = sum(_embed_chars(e) for e in embeds)

    return embeds


def build_error_embed(msg: str) -> dict:
    return {
        "author": {"name": "\u26a0\ufe0f Stand-up Report"},
        "title": "Error \u2014 Could not fetch data",
        "description": f"```\n{msg}\n```",
        "color": 0xEF4444,
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
    files = sorted(latest.glob("*/*.jpg"))
    log.info("Found %d job card(s) in %s", len(files), latest.name)
    return files


# ── Image compression ──────────────────────────────
def compress_jobcards(files: list[Path], quality: int = 65, max_width: int = 1600) -> list[Path]:
    """Compress job card images to reduce Discord upload size. Returns paths to compressed files."""
    try:
        from PIL import Image
    except ImportError:
        log.warning("Pillow not installed, skipping compression")
        return files

    # Save compressed files next to the originals
    out_dir = files[0].parents[1] / "compressed"
    out_dir.mkdir(parents=True, exist_ok=True)
    compressed = []

    for f in files:
        try:
            img = Image.open(f)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            w, h = img.size
            if w > max_width:
                ratio = max_width / w
                img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)

            out_path = out_dir / f"{f.stem}.jpg"
            img.save(out_path, "JPEG", quality=quality, optimize=True)

            before = f.stat().st_size
            after = out_path.stat().st_size
            log.info("Compressed %s: %s → %s (%.0f%% smaller)", f.name,
                     _get_size_str(before), _get_size_str(after), (1 - after / before) * 100)
            compressed.append(out_path)
        except Exception as e:
            log.warning("Failed to compress %s: %s, using original", f.name, e)
            compressed.append(f)

    return compressed


def _get_size_str(size_bytes: int) -> str:
    """Format file size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / 1024 / 1024:.1f} MB"


# ── Discord Webhook ─────────────────────────────────
def _webhook_payload(embeds: list[dict]) -> dict:
    """Build the webhook JSON payload with bot identity."""
    data: dict = {"embeds": embeds, "username": BOT_USERNAME}
    if BOT_AVATAR_URL:
        data["avatar_url"] = BOT_AVATAR_URL
    return data


def _send_to_url(url: str, embeds: list[dict], files: list[Path] | None = None):
    """Send embeds to a single Discord webhook URL."""
    if not files:
        payload = json.dumps(_webhook_payload(embeds)).encode()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "StandupBot/1.0",
        }
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                log.info("Webhook sent to %s (status %s)", url[:60], resp.status)
        except urllib.error.HTTPError as e:
            log.error("Webhook error %s → %s: %s", url[:60], e.code, e.read().decode()[:200])
        except (urllib.error.URLError, OSError) as e:
            log.error("Webhook connection error %s: %s", url[:60], e)
        return

    # Multipart form-data for file attachments
    boundary = uuid.uuid4().hex
    body = b""

    # payload_json part
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="payload_json"\r\n'
    body += b"Content-Type: application/json\r\n\r\n"
    body += json.dumps(_webhook_payload(embeds)).encode()
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
        req = urllib.request.Request(url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            log.info("Webhook sent with %d file(s) to %s (status %s)", len(files), url[:60], resp.status)
    except urllib.error.HTTPError as e:
        log.error("Webhook error %s → %s: %s", url[:60], e.code, e.read().decode()[:200])
    except (urllib.error.URLError, OSError) as e:
        log.error("Webhook connection error %s: %s", url[:60], e)


def send_webhook(embeds: list[dict], files: list[Path] | None = None):
    """Send embeds to all configured Discord webhook URLs."""
    for url in WEBHOOK_URLS:
        _send_to_url(url, embeds, files)


# ── Post standup ────────────────────────────────────
def post_standup():
    """Fetch Jira data and post to Discord with job card attachments."""
    issues = fetch_jira_issues()
    if issues is None:
        send_webhook([build_error_embed("Jira API request failed")])
        return

    embeds = build_standup_embeds(issues)
    jobcards = find_latest_jobcards()
    if jobcards:
        jobcards = compress_jobcards(jobcards, quality=60, max_width=1400)
    send_webhook(embeds, files=jobcards or None)
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
