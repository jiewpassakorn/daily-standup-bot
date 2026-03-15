import json
import re
import time
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


def load_urls() -> dict:
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
    remove_images: bool = False,
    print_range: str | None = None,
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
            print_range=print_range,
        )
        try:
            download_pdf(export_url, pdf_path, session=session)
            rprint(f"  Saved: {pdf_path} ({attempt['label']})")
            break
        except HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                for retry in range(3):
                    wait = 10 * (retry + 1)
                    rprint(f"  [yellow]Rate limited, retrying in {wait}s... ({retry + 1}/3)[/yellow]")
                    time.sleep(wait)
                    try:
                        download_pdf(export_url, pdf_path, session=session)
                        rprint(f"  Saved: {pdf_path} ({attempt['label']})")
                        break
                    except HTTPError as retry_e:
                        if retry_e.response is not None and retry_e.response.status_code == 429 and retry < 2:
                            continue
                        raise
                else:
                    continue
                break
            elif e.response is not None and e.response.status_code == 500 and i < len(export_attempts) - 1:
                rprint(f"  [yellow]{attempt['label']} failed (500), trying next...[/yellow]")
            else:
                raise

    rprint(f"[bold]Converting to images ({dpi} DPI, {fmt.upper()})...[/bold]")
    page_count, saved = process_pdf(
        pdf_path, output_dir, dpi=dpi, fmt=fmt, merge=True, prefix=prefix,
        max_width=max_width, remove_images=remove_images,
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
    remove_images: Annotated[bool, typer.Option("--remove-images", help="Remove embedded images from the sheet")] = False,
    print_range: Annotated[Optional[str], typer.Option("--range", help="Print range e.g. A1:R100")] = None,
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
        table.add_column("URL / Tabs")
        for n, u in urls.items():
            if isinstance(u, dict) and "url" in u:
                opts = [k for k in u if k != "url"]
                opts_str = f" [dim]({', '.join(opts)})[/dim]" if opts else ""
                table.add_row(n, u["url"] + opts_str)
            elif isinstance(u, dict):
                table.add_row(n, f"[dim]({len(u)} tabs)[/dim]")
                for tab_name in u:
                    table.add_row(f"  {tab_name}", "")
            else:
                table.add_row(n, u)
        rprint(table)
        raise typer.Exit()

    if name:
        _validate_path_component(name, "name")
        urls = load_urls()
        if name not in urls:
            rprint(f"[red]Error:[/red] '{name}' not found. Use --list to see saved URLs.")
            raise typer.Exit(1)
        entry = urls[name]

        # Single URL with options: dict with "url" key
        if isinstance(entry, dict) and "url" in entry:
            url = entry["url"]
            print_range = print_range or entry.get("range")
            portrait = entry.get("portrait", portrait)
            rprint(f"[dim]Using saved URL: {name}[/dim]")

        # Group: dict of tab_name → url/config
        elif isinstance(entry, dict):
            default_range = entry.get("_default_range", print_range)
            tabs = {k: v for k, v in entry.items() if not k.startswith("_")}

            rprint(f"[dim]Using saved group: {name} ({len(tabs)} tabs)[/dim]")
            if default_range:
                rprint(f"[dim]  Default range: {default_range}[/dim]")

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
            now = datetime.now()
            ts = timestamp or now.strftime("%Y%m%d_%H%M%S")
            date_str = ts[:8]
            output_dir = Path(output) / ts / name

            for i, (tab_name, tab_config) in enumerate(tabs.items()):
                if i > 0:
                    rprint("[dim]  Waiting 5s to avoid rate limit...[/dim]")
                    time.sleep(5)
                rprint(f"\n[bold cyan]━━━ {tab_name} ━━━[/bold cyan]")

                # Support both string (url only) and dict (url + range)
                if isinstance(tab_config, str):
                    tab_url = tab_config
                    tab_range = default_range
                else:
                    tab_url = tab_config["url"]
                    tab_range = tab_config.get("range", default_range)

                prefix = f"{date_str}_{tab_name}"
                try:
                    capture(
                        tab_url, session, output_dir, dpi, fmt, portrait,
                        prefix=prefix, max_width=max_width,
                        remove_images=remove_images, print_range=tab_range,
                    )
                except Exception as e:
                    rprint(f"  [red]FAILED: {tab_name} — {e}[/red]")

            rprint(f"\n[bold green]All done![/bold green] {len(tabs)} tabs in {output_dir}/")
            raise typer.Exit()

        else:
            url = entry
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
        prefix=prefix, max_width=max_width, remove_images=remove_images,
        print_range=print_range,
    )


if __name__ == "__main__":
    app()
