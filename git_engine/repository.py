"""Repository detection and metadata inspection."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from git_engine.exceptions import (
    GitCommandError,
    GitError,
    GitExecutableNotFoundError,
    InvalidRepositoryPathError,
    NotAGitRepositoryError,
)
from git_engine.models import RepositoryInfo


def _ensure_git_executable() -> str:
    """Verify that git executable exists in PATH."""
    git_bin = shutil.which("git")
    if not git_bin:
        raise GitExecutableNotFoundError()
    return git_bin


def _run_git_command(
    args: List[str],
    cwd: Optional[str] = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Execute a git command using subprocess without shell=True."""
    git_bin = _ensure_git_executable()
    target_dir = str(Path(cwd).resolve()) if cwd else str(Path.cwd())

    if not Path(target_dir).is_dir():
        raise InvalidRepositoryPathError(target_dir)

    try:
        proc = subprocess.run(
            [git_bin] + args,
            cwd=target_dir,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise GitError(f"Failed to execute git process: {exc}") from exc

    if check and proc.returncode != 0:
        raise GitCommandError(
            command=[git_bin] + args,
            returncode=proc.returncode,
            stderr=proc.stderr,
            stdout=proc.stdout,
        )

    return proc


def is_git_repository(path: Optional[str] = None) -> bool:
    """Detect whether the directory belongs to a Git repository."""
    try:
        proc = _run_git_command(
            ["rev-parse", "--is-inside-work-tree"],
            cwd=path,
            check=False,
        )
        return proc.returncode == 0 and "true" in proc.stdout.strip().lower()
    except (GitError, InvalidRepositoryPathError):
        return False


def get_repository_root(path: Optional[str] = None) -> str:
    """Retrieve the absolute root path of the Git repository."""
    target_dir = str(Path(path).resolve()) if path else str(Path.cwd())
    if not Path(target_dir).is_dir():
        raise InvalidRepositoryPathError(target_dir)

    proc = _run_git_command(
        ["rev-parse", "--show-toplevel"],
        cwd=target_dir,
        check=False,
    )
    if proc.returncode != 0:
        raise NotAGitRepositoryError(target_dir)

    return str(Path(proc.stdout.strip()).resolve())


def get_git_version() -> str:
    """Retrieve the installed Git version string."""
    proc = _run_git_command(["--version"], check=False)
    if proc.returncode == 0:
        return proc.stdout.strip()
    return "unknown"


def get_current_branch(path: Optional[str] = None) -> Optional[str]:
    """Retrieve the name of the current active branch, or None if detached/unborn."""
    # First try symbolic-ref
    proc = _run_git_command(
        ["symbolic-ref", "--short", "-q", "HEAD"],
        cwd=path,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()

    # If symbolic-ref failed, try branch --show-current
    proc2 = _run_git_command(
        ["branch", "--show-current"],
        cwd=path,
        check=False,
    )
    if proc2.returncode == 0 and proc2.stdout.strip():
        return proc2.stdout.strip()

    return None


def get_current_commit(path: Optional[str] = None) -> Optional[str]:
    """Retrieve the current HEAD commit hash, or None if repository has no commits."""
    proc = _run_git_command(
        ["rev-parse", "--verify", "HEAD"],
        cwd=path,
        check=False,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def is_detached_head(path: Optional[str] = None) -> bool:
    """Detect whether repository is in a detached HEAD state."""
    # Check if we have at least one commit
    commit = get_current_commit(path=path)
    if not commit:
        # Repository without commits is unborn, not detached
        return False

    # In detached HEAD, symbolic-ref fails
    proc = _run_git_command(
        ["symbolic-ref", "-q", "HEAD"],
        cwd=path,
        check=False,
    )
    return proc.returncode != 0


def get_repository_info(path: Optional[str] = None) -> RepositoryInfo:
    """Gather complete metadata for the target Git repository."""
    target_dir = str(Path(path).resolve()) if path else str(Path.cwd())
    if not Path(target_dir).is_dir():
        raise InvalidRepositoryPathError(target_dir)

    if not is_git_repository(target_dir):
        raise NotAGitRepositoryError(target_dir)

    root_path = get_repository_root(target_dir)
    branch = get_current_branch(root_path)
    commit = get_current_commit(root_path)
    git_ver = get_git_version()
    detached = is_detached_head(root_path)

    return RepositoryInfo(
        root_path=root_path,
        current_branch=branch,
        current_commit=commit,
        git_version=git_ver,
        is_detached=detached,
    )
