import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import requests
import typer
from requests.exceptions import HTTPError
from rich import print as rprint
from rich.table import Table

from converter import process_pdf
from gsheet import build_export_url, create_session, download_pdf, parse_url

URLS_FILE = Path(".urls.json")

app = typer.Typer(help="Export Google Sheets as email-friendly images.")


def load_urls() -> dict[str, str]:
    if URLS_FILE.is_file():
        return json.loads(URLS_FILE.read_text())
    return {}


def save_url(name: str, url: str) -> None:
    urls = load_urls()
    urls[name] = url
    URLS_FILE.write_text(json.dumps(urls, indent=2, ensure_ascii=False))


def _validate_path_component(value: str, label: str) -> None:
    if re.search(r"[/\\]", value) or ".." in value:
        rprint(f"[red]Error:[/red] --{label} must not contain '/', '\\\\' or '..'")
        raise typer.Exit(1)


def capture(
    url: str,
    session: requests.Session,
    output_dir: Path,
    dpi: int,
    fmt: str,
    portrait: bool,
    prefix: str,
    max_width: int | None,
) -> None:
    rprint("[bold]Parsing URL...[/bold]")
    spreadsheet_id, gid = parse_url(url)
    rprint(f"  Spreadsheet ID: {spreadsheet_id}")
    rprint(f"  GID: {gid}")

    pdf_path = output_dir / "sheet.pdf"

    export_attempts = [
        {"scale": 2, "paper_size": 6, "label": "A3 fit-to-width"},
        {"scale": 1, "paper_size": 6, "label": "A3 normal"},
        {"scale": 4, "paper_size": 6, "label": "A3 fit-to-page"},
    ]

    rprint("[bold]Downloading PDF...[/bold]")
    for i, attempt in enumerate(export_attempts):
        export_url = build_export_url(
            spreadsheet_id, gid, portrait=portrait,
            scale=attempt["scale"], paper_size=attempt["paper_size"],
        )
        try:
            download_pdf(export_url, pdf_path, session=session)
            rprint(f"  Saved: {pdf_path} ({attempt['label']})")
            break
        except HTTPError as e:
            if e.response is not None and e.response.status_code == 500 and i < len(export_attempts) - 1:
                rprint(f"  [yellow]{attempt['label']} failed (500), trying next...[/yellow]")
            else:
                raise

    rprint(f"[bold]Converting to images ({dpi} DPI, {fmt.upper()})...[/bold]")
    page_count, saved = process_pdf(
        pdf_path, output_dir, dpi=dpi, fmt=fmt, merge=True, prefix=prefix,
        max_width=max_width,
    )
    rprint(f"  Pages found: {page_count}")
    for path in saved:
        rprint(f"  Saved: {path}")

    pdf_path.unlink()
    rprint(f"[bold green]Done![/bold green] {len(saved)} files in {output_dir}/")


@app.command()
def main(
    url: Annotated[Optional[str], typer.Option(help="Google Sheet URL")] = None,
    name: Annotated[Optional[str], typer.Option(help="Use a saved URL by name")] = None,
    save: Annotated[Optional[str], typer.Option(help="Save this URL with a name for reuse")] = None,
    list_urls: Annotated[bool, typer.Option("--list", help="List all saved URLs")] = False,
    credentials: Annotated[Optional[str], typer.Option(help="Path to service account JSON (default: .credentials.json)")] = None,
    dpi: Annotated[int, typer.Option(help="Image DPI")] = 150,
    fmt: Annotated[str, typer.Option("--format", help="Output format: png or jpg")] = "jpg",
    portrait: Annotated[bool, typer.Option(help="Use portrait orientation (default: landscape)")] = False,
    max_width: Annotated[Optional[int], typer.Option(help="Max image width in pixels")] = 1600,
    timestamp: Annotated[Optional[str], typer.Option(help="Shared timestamp for batch runs")] = None,
    output: Annotated[str, typer.Option(help="Output directory")] = "./output",
) -> None:
    if list_urls:
        urls = load_urls()
        if not urls:
            rprint("[dim]No saved URLs yet. Use --save <name> to save one.[/dim]")
            raise typer.Exit()
        table = Table(title="Saved URLs")
        table.add_column("Name", style="bold cyan")
        table.add_column("URL")
        for n, u in urls.items():
            table.add_row(n, u)
        rprint(table)
        raise typer.Exit()

    if name:
        _validate_path_component(name, "name")
        urls = load_urls()
        if name not in urls:
            rprint(f"[red]Error:[/red] '{name}' not found. Use --list to see saved URLs.")
            raise typer.Exit(1)
        url = urls[name]
        rprint(f"[dim]Using saved URL: {name}[/dim]")

    if not url:
        rprint("[red]Error:[/red] --url or --name is required.")
        raise typer.Exit(1)

    if save:
        _validate_path_component(save, "save")
        save_url(save, url)
        rprint(f"[bold green]Saved![/bold green] '{save}' → {url}")

    if fmt not in ("png", "jpg"):
        rprint(f"[red]Error:[/red] --format must be 'png' or 'jpg', got '{fmt}'")
        raise typer.Exit(1)

    if timestamp:
        _validate_path_component(timestamp, "timestamp")

    credentials_path = credentials
    if not credentials_path:
        default_creds = Path(".credentials.json")
        if default_creds.is_file():
            credentials_path = str(default_creds)

    session = create_session(credentials_path)

    project_name = name or save or "sheet"
    now = datetime.now()
    ts = timestamp or now.strftime("%Y%m%d_%H%M%S")
    date_str = ts[:8]
    prefix = f"{date_str}_{project_name}_job-card"
    output_dir = Path(output) / ts / project_name

    capture(
        url, session, output_dir, dpi, fmt, portrait,
        prefix=prefix, max_width=max_width,
    )


if __name__ == "__main__":
    app()
