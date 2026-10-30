"""Git status extraction and parsing."""

from pathlib import Path
from typing import List, Optional

from git_engine.exceptions import GitCommandError, GitError
from git_engine.models import FileChange
from git_engine.repository import _run_git_command, get_repository_root


CONFLICT_CODES = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}


def parse_porcelain_status(status_bytes_or_str: str) -> List[FileChange]:
    """Parse git status --porcelain=v1 -z output into FileChange objects."""
    changes: List[FileChange] = []
    if not status_bytes_or_str:
        return changes

    # In -z format, entries are separated by null bytes (\0)
    parts = status_bytes_or_str.split("\0")
    idx = 0
    total = len(parts)

    while idx < total:
        entry = parts[idx]
        if not entry:
            idx += 1
            continue

        if len(entry) < 3:
            idx += 1
            continue

        x = entry[0]
        y = entry[1]
        path = entry[3:]  # Format is "XY <path>"

        # Check for ignored files (e.g. "!!")
        if x == "!" and y == "!":
            idx += 1
            continue

        # Check for untracked files ("??")
        if x == "?" and y == "?":
            changes.append(
                FileChange(
                    file_path=path,
                    change_type="untracked",
                    is_untracked=True,
                    is_staged=False,
                    is_unstaged=True,
                )
            )
            idx += 1
            continue

        # Check for merge conflicts
        is_conflicted = (
            f"{x}{y}" in CONFLICT_CODES
            or x == "U"
            or y == "U"
        )

        old_path: Optional[str] = None
        new_path: Optional[str] = None

        # Check for renames or copies: in -z format, next null-delimited token is the old path
        if x in ("R", "C") or y in ("R", "C"):
            if idx + 1 < total:
                old_path = parts[idx + 1]
                new_path = path
                idx += 1  # Consume the extra token
            else:
                new_path = path

        # Determine change type
        if is_conflicted:
            change_type = "conflicted"
        elif x == "R" or y == "R":
            change_type = "renamed"
        elif x == "C" or y == "C":
            change_type = "copied"
        elif x == "D" or y == "D":
            change_type = "deleted"
        elif x == "A":
            change_type = "added"
        else:
            change_type = "modified"

        is_staged = x in ("M", "A", "D", "R", "C")
        is_unstaged = y in ("M", "D")

        changes.append(
            FileChange(
                file_path=new_path or path,
                old_path=old_path,
                new_path=new_path,
                change_type=change_type,
                is_staged=is_staged,
                is_unstaged=is_unstaged,
                is_untracked=False,
                is_binary=False,
            )
        )
        idx += 1

    return changes


def get_repository_status(path: Optional[str] = None) -> List[FileChange]:
    """Execute git status --porcelain=v1 -z and return structured FileChange objects."""
    root = get_repository_root(path)
    proc = _run_git_command(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        check=True,
    )
    return parse_porcelain_status(proc.stdout)


def get_staged_changes(changes: List[FileChange]) -> List[FileChange]:
    """Filter changes to include only those with staged modifications."""
    return [c for c in changes if c.is_staged]


def get_unstaged_changes(changes: List[FileChange]) -> List[FileChange]:
    """Filter changes to include only those with unstaged modifications."""
    return [c for c in changes if c.is_unstaged]


def get_untracked_files(changes: List[FileChange]) -> List[FileChange]:
    """Filter changes to include only untracked files."""
    return [c for c in changes if c.is_untracked]


def get_conflicted_files(changes: List[FileChange]) -> List[FileChange]:
    """Filter changes to include only conflicted files."""
    return [c for c in changes if c.change_type == "conflicted"]
