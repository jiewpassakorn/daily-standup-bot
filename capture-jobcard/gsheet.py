import json
import re
from pathlib import Path
from urllib.parse import urlencode

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def parse_url(url: str) -> tuple[str, str]:
    """Extract spreadsheet ID and gid from a Google Sheets URL.

    Supports:
      - /d/{ID}/edit#gid=123  (fragment)
      - /d/{ID}/edit?gid=123  (query param)
      - /d/{ID}/edit          (no gid → default "0")
    """
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Invalid Google Sheets URL: {url}")
    spreadsheet_id = match.group(1)

    gid_match = re.search(r"[#?&]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else "0"

    return spreadsheet_id, gid


def build_export_url(
    spreadsheet_id: str,
    gid: str,
    portrait: bool = False,
    scale: int = 4,
    paper_size: int = 6,
) -> str:
    """Build the Google Sheets PDF export URL with zero margins.

    Scale: 1=Normal 100%, 2=Fit to width, 3=Fit to height, 4=Fit to page
    Paper: 0=Letter, 1=Tabloid, 2=Legal, 6=A3, 7=A4
    """
    base = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
    params = urlencode({
        "format": "pdf",
        "gid": gid,
        "size": paper_size,
        "portrait": "true" if portrait else "false",
        "scale": scale,
        "fitw": "true",
        "sheetnames": "false",
        "printtitle": "false",
        "pagenumbers": "false",
        "gridlines": "false",
        "fzr": "false",
        "fzc": "false",
        "top_margin": "0",
        "bottom_margin": "0",
        "left_margin": "0",
        "right_margin": "0",
    })
    return f"{base}?{params}"


def create_session(credentials_file: str | None = None) -> requests.Session:
    """Create an authenticated session.

    If credentials_file is provided, uses Google Service Account auth.
    Otherwise, returns a plain requests.Session (for public sheets).
    """
    if credentials_file:
        path = Path(credentials_file).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Credentials file not found: {path}")
        credentials = service_account.Credentials.from_service_account_file(
            str(path), scopes=SCOPES
        )
        return AuthorizedSession(credentials)
    return requests.Session()


def download_pdf(export_url: str, output_path: Path, session: requests.Session | None = None) -> None:
    """Download the PDF from Google Sheets export URL."""
    s = session or requests.Session()
    response = s.get(export_url, timeout=(30, 60))
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "text/html" in content_type:
        raise RuntimeError(
            "Got HTML instead of PDF — credentials may be invalid or sheet not shared with service account."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)


def test_auth(urls_file: str = ".urls.json", credentials_file: str | None = None) -> tuple[bool, str]:
    """Test authentication against the first saved URL. Returns (ok, project_name)."""
    with open(urls_file) as f:
        urls = json.load(f)
    name, url = next(iter(urls.items()))
    sid, gid = parse_url(url)
    export_url = build_export_url(sid, gid)
    session = create_session(credentials_file)
    r = session.get(export_url, timeout=(10, 30))
    ct = r.headers.get("Content-Type", "")
    return "application/pdf" in ct, name
