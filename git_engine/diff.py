"""Git diff extraction for staged, unstaged, and untracked changes."""

from pathlib import Path
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from config.settings import Settings, get_settings
from git_engine.exceptions import DiffExtractionError
from git_engine.repository import _run_git_command, get_current_commit, get_repository_root
from git_engine.status import get_untracked_files, parse_porcelain_status


class ExtractedDiffs(BaseModel):
    """Container for extracted diff texts and metadata."""

    unstaged_diff: str = Field(default="", description="Diff of unstaged working tree changes")
    staged_diff: str = Field(default="", description="Diff of staged index changes")
    combined_diff: str = Field(default="", description="Diff of tracked changes relative to HEAD")
    untracked_diff: str = Field(default="", description="Synthetic diff for untracked files")
    is_truncated: bool = Field(default=False, description="True if diff was truncated due to size limits")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }


def is_binary_file(file_path: Path) -> bool:
    """Check if a file appears to be binary by looking for null bytes in initial chunk."""
    if not file_path.is_file():
        return False
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return False


def get_unstaged_diff(path: Optional[str] = None) -> str:
    """Extract unstaged diff in the working tree."""
    root = get_repository_root(path)
    proc = _run_git_command(
        ["diff", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=root,
        check=False,
    )
    if proc.returncode != 0:
        raise DiffExtractionError(f"git diff exited with code {proc.returncode}: {proc.stderr}")
    return proc.stdout


def get_staged_diff(path: Optional[str] = None) -> str:
    """Extract staged diff in the Git index."""
    root = get_repository_root(path)
    proc = _run_git_command(
        ["diff", "--cached", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=root,
        check=False,
    )
    if proc.returncode != 0:
        raise DiffExtractionError(f"git diff --cached exited with code {proc.returncode}: {proc.stderr}")
    return proc.stdout


def get_combined_tracked_diff(path: Optional[str] = None) -> str:
    """Extract combined tracked diff relative to HEAD (or fallback to staged if no HEAD)."""
    root = get_repository_root(path)
    head_commit = get_current_commit(root)
    if not head_commit:
        # Initial repository without commits: diff relative to empty tree (cached diff)
        return get_staged_diff(root)

    proc = _run_git_command(
        ["diff", "HEAD", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=root,
        check=False,
    )
    if proc.returncode != 0:
        raise DiffExtractionError(f"git diff HEAD exited with code {proc.returncode}: {proc.stderr}")
    return proc.stdout


def generate_untracked_diff(
    untracked_relative_paths: List[str],
    root_path: Path,
    max_size: int = 100000,
    current_size: int = 0,
) -> Tuple[str, bool]:
    """Generate synthetic unified diffs for untracked files without modifying index or working tree.

    Returns:
        Tuple of (diff_content, is_truncated).
    """
    diff_blocks: List[str] = []
    accumulated_size = current_size
    truncated = False

    for rel_path in untracked_relative_paths:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue

        norm_rel = rel_path.replace("\\", "/")

        if is_binary_file(full_path):
            block = (
                f"diff --git a/{norm_rel} b/{norm_rel}\n"
                f"new file mode 100644\n"
                f"Binary files /dev/null and b/{norm_rel} differ\n"
            )
            if accumulated_size + len(block) > max_size:
                truncated = True
                break
            diff_blocks.append(block)
            accumulated_size += len(block)
            continue

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except (OSError, PermissionError):
            continue

        num_lines = len(lines)
        if num_lines == 0:
            header = (
                f"diff --git a/{norm_rel} b/{norm_rel}\n"
                f"new file mode 100644\n"
                f"--- /dev/null\n"
                f"+++ b/{norm_rel}\n"
            )
            if accumulated_size + len(header) > max_size:
                truncated = True
                break
            diff_blocks.append(header)
            accumulated_size += len(header)
            continue

        header = (
            f"diff --git a/{norm_rel} b/{norm_rel}\n"
            f"new file mode 100644\n"
            f"--- /dev/null\n"
            f"+++ b/{norm_rel}\n"
            f"@@ -0,0 +1,{num_lines} @@\n"
        )
        content_lines = ["+" + line if line.endswith("\n") else "+" + line + "\n" for line in lines]
        block = header + "".join(content_lines)

        if accumulated_size + len(block) > max_size:
            # Check if we can include a partial truncated block or if we stop
            truncated = True
            break

        diff_blocks.append(block)
        accumulated_size += len(block)

    return "".join(diff_blocks), truncated


def extract_all_diffs(
    path: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> ExtractedDiffs:
    """Extract staged, unstaged, and untracked diffs with size enforcement."""
    cfg = settings or get_settings()
    max_size = cfg.max_diff_size
    root = Path(get_repository_root(path))

    unstaged = get_unstaged_diff(str(root))
    staged = get_staged_diff(str(root))
    combined = get_combined_tracked_diff(str(root))

    # Retrieve untracked files safely from git status (which respects .gitignore)
    proc_status = _run_git_command(
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=str(root),
        check=True,
    )
    status_changes = parse_porcelain_status(proc_status.stdout)
    untracked_paths = [c.file_path for c in status_changes if c.is_untracked]

    total_tracked_len = len(unstaged) + len(staged)
    is_truncated = False

    if total_tracked_len >= max_size:
        is_truncated = True
        untracked = ""
    else:
        untracked, un_truncated = generate_untracked_diff(
            untracked_relative_paths=untracked_paths,
            root_path=root,
            max_size=max_size,
            current_size=total_tracked_len,
        )
        if un_truncated:
            is_truncated = True

    return ExtractedDiffs(
        unstaged_diff=unstaged,
        staged_diff=staged,
        combined_diff=combined,
        untracked_diff=untracked,
        is_truncated=is_truncated,
    )
