"""Commit Surgeon - CLI Entry Point.

AI-powered offline Git commit management tool.
"""

import sys
from pathlib import Path
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel

from config.settings import get_settings
from git_engine.analyzer import analyze_repository
from git_engine.exceptions import GitError, GitExecutableNotFoundError, NotAGitRepositoryError
from utils.environment import run_environment_check


def run_environment_check_cli() -> int:
    """Execute the Commit Surgeon initial CLI and environment check."""
    console = Console()
    settings = get_settings()

    # Perform environment checks (no git modifications)
    report = run_environment_check(settings=settings)

    # Style status labels
    py_style = "bold green" if report.python.is_ok else "bold red"
    git_style = "bold green" if report.git.is_ok else "bold red"
    ollama_style = "bold green" if report.ollama.is_ok else "bold red"
    if report.model.label == "Available":
        model_style = "bold green"
    elif report.model.label == "Unknown":
        model_style = "bold yellow"
    else:
        model_style = "bold red"

    console.print()
    console.print("[bold cyan]COMMIT SURGEON[/bold cyan]")
    console.print("AI-powered offline Git commit management\n")
    console.print(f"Version: {settings.app_version}\n")
    console.print("Environment Status:")
    console.print(f"- Python: [{py_style}]{report.python.label}[/{py_style}]")
    console.print(f"- Git: [{git_style}]{report.git.label}[/{git_style}]")
    console.print(f"- Ollama: [{ollama_style}]{report.ollama.label}[/{ollama_style}]")
    console.print(f"- Local Model: [{model_style}]{report.model.label}[/{model_style}]\n")

    status_suffix = (
        "[bold green]Ready[/bold green]"
        if report.all_ready
        else "[bold yellow]Setup Required[/bold yellow]"
    )
    console.print(
        f"Project Status: [bold blue]Environment Check Complete[/bold blue] ({status_suffix})\n"
    )

    # If any component requires user setup, provide clear offline instructions
    guidance = []
    if not report.ollama.is_ok:
        guidance.append(
            "[bold yellow]Ollama Service:[/bold yellow]\n"
            "  Ollama is not running. Start the service with:\n"
            "    [green]ollama serve[/green]\n"
            "  Or launch the Ollama desktop application."
        )

    if report.model.label == "Unknown":
        guidance.append(
            f"[bold yellow]Local Model ({settings.default_model}):[/bold yellow]\n"
            f"  Model availability is currently unknown because Ollama is not running.\n"
            f"  [cyan]{settings.default_model}[/cyan] is a 4-billion (4B) parameter model designed for "
            f"fast, lightweight, offline inference.\n"
            f"  Once Ollama is started, download and verify the model with:\n"
            f"    [green]ollama pull {settings.default_model}[/green]\n"
            f"  Commit Surgeon will not automatically download models to respect your bandwidth and offline workflow."
        )
    elif not report.model.is_ok:
        guidance.append(
            f"[bold yellow]Local Model ({settings.default_model}):[/bold yellow]\n"
            f"  The model is not available locally in Ollama.\n"
            f"  [cyan]{settings.default_model}[/cyan] is a 4-billion (4B) parameter model designed for "
            f"fast, lightweight, offline inference.\n"
            f"  To download and prepare the model manually, run:\n"
            f"    [green]ollama pull {settings.default_model}[/green]\n"
            f"  Commit Surgeon will not automatically download models to respect your bandwidth and offline workflow."
        )

    if guidance:
        content = "\n\n".join(guidance)
        console.print(
            Panel(
                content,
                title="[bold yellow]Action Required / Recommendations[/bold yellow]",
                border_style="yellow",
            )
        )

    return 0


def run_analyze(path: Optional[str] = None) -> int:
    """Execute repository change analysis and display report using Rich."""
    console = Console()
    settings = get_settings()

    try:
        changes = analyze_repository(path=path, settings=settings)
    except NotAGitRepositoryError:
        console.print("[bold red]Error:[/bold red] Current directory is not a Git repository.")
        return 1
    except GitExecutableNotFoundError:
        console.print("[bold red]Error:[/bold red] Git executable 'git' not found in PATH.")
        return 1
    except GitError as exc:
        console.print(f"[bold red]Git Error:[/bold red] {exc}")
        return 1

    repo_name = Path(changes.repository.root_path).name
    branch_name = changes.repository.current_branch or "DETACHED HEAD / UNBORN"

    console.print()
    console.print("[bold cyan]COMMIT SURGEON[/bold cyan]")
    console.print("Git Change Analysis\n")
    console.print(f"Repository: [bold]{repo_name}[/bold]")
    console.print(f"Branch: [bold]{branch_name}[/bold]\n")

    console.print("Detected Changes:\n")
    console.print(f"Modified: {changes.modified_count}")
    console.print(f"Added: {changes.added_count}")
    console.print(f"Deleted: {changes.deleted_count}")
    console.print(f"Renamed: {changes.renamed_count}")
    console.print(f"Untracked: {changes.untracked_count}\n")

    console.print("Diff Statistics:\n")
    console.print("Staged:")
    console.print(f"- Added lines: {changes.staged_added_lines}")
    console.print(f"- Deleted lines: {changes.staged_deleted_lines}\n")
    console.print("Unstaged:")
    console.print(f"- Added lines: {changes.unstaged_added_lines}")
    console.print(f"- Deleted lines: {changes.unstaged_deleted_lines}\n")
    console.print("Total:")
    console.print(f"- Added lines: {changes.total_added_lines}")
    console.print(f"- Deleted lines: {changes.total_deleted_lines}")
    console.print(f"- Hunks: {changes.total_hunks}\n")

    if changes.has_conflicts:
        console.print("[bold yellow]Warning:[/bold yellow] Unresolved merge conflicts detected in working tree.\n")

    if changes.has_truncated_content:
        console.print(
            f"[bold yellow]Notice:[/bold yellow] Diff output exceeded maximum size limit "
            f"({settings.max_diff_size} chars) and was truncated.\n"
        )

    console.print("[bold green]Analysis completed successfully.[/bold green]\n")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point for Commit Surgeon."""
    args = argv if argv is not None else sys.argv[1:]
    if args and args[0].strip().lower() == "analyze":
        target_path = args[1] if len(args) > 1 else None
        return run_analyze(path=target_path)
    return run_environment_check_cli()


if __name__ == "__main__":
    sys.exit(main())
