from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .client import GitHubClient
from .errors import GhLensError
from .formatters import get_formatter

_stderr = Console(stderr=True)


load_dotenv()


@click.group()
def cli() -> None:
    """ghlens — fetch PR metadata and comments from GitHub."""


@cli.command()
@click.argument("repo", metavar="OWNER/REPO")
@click.option(
    "--state",
    type=click.Choice(["OPEN", "CLOSED", "MERGED", "ALL"]),
    default="ALL",
    show_default=True,
    help="Filter PRs by state.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "markdown"]),
    default="json",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write output to a file instead of stdout.",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=None,
    help="Maximum number of PRs to fetch.",
)
def fetch(
    repo: str,
    state: str,
    output_format: str,
    output_path: Path | None,
    limit: int | None,
) -> None:
    """Fetch pull requests and their comments from OWNER/REPO."""
    # Validate OWNER/REPO format
    if "/" not in repo or repo.count("/") != 1:
        raise click.BadParameter(
            f"{repo!r} is not a valid OWNER/REPO format.",
            param_hint="REPO",
        )
    owner, repo_name = repo.split("/", 1)
    if not owner or not repo_name:
        raise click.BadParameter(
            f"{repo!r} is not a valid OWNER/REPO format.",
            param_hint="REPO",
        )

    # Read GitHub token
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        _stderr.print("[red]Error:[/red] GITHUB_TOKEN environment variable is not set.")
        sys.exit(1)

    # Determine states
    if state == "ALL":
        states = ["OPEN", "CLOSED", "MERGED"]
    else:
        states = [state]

    prs = []
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=_stderr,
            transient=True,
        ) as progress:
            task_id = progress.add_task(f"Fetching PRs from {repo}…", total=None)
            with GitHubClient(token) as client:
                for pr in client.fetch_prs(owner, repo_name, states, limit):
                    prs.append(pr)
                    progress.update(task_id, description=f"Fetched {len(prs)} PRs from {repo}…")
    except GhLensError as exc:
        _stderr.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    formatter = get_formatter(output_format, owner_repo=repo)
    output = formatter(prs)

    if output_path is not None:
        output_path.write_text(output, encoding="utf-8")
        _stderr.print(f"[green]Wrote {len(prs)} PRs to {output_path}[/green]")
    else:
        click.echo(output)
