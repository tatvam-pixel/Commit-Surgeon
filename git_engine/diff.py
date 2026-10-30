"""Git diff extraction for staged, unstaged, and untracked changes."""

import os
import subprocess
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


def _run_git_diff_bounded(
    cmd: List[str],
    cwd: str,
    max_chars: int,
    encoding: str = "utf-8",
) -> Tuple[str, bool]:
    """Execute a git diff command while strictly bounding memory consumption.

    Reads output incrementally in chunks from subprocess.stdout up to max_chars.
    If the output exceeds max_chars, terminates the subprocess immediately to
    prevent unbounded memory growth and unnecessary CPU cycles.

    Returns:
        Tuple of (diff_output_text, is_truncated)
    """
    if max_chars <= 0:
        return "", True

    full_cmd = ["git"] + cmd
    try:
        proc = subprocess.Popen(
            full_cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=8192,
        )
    except FileNotFoundError:
        from git_engine.exceptions import GitExecutableNotFoundError
        raise GitExecutableNotFoundError()
    except Exception as exc:
        raise DiffExtractionError(f"Failed to start git command {' '.join(cmd)}: {exc}")

    output_chunks: List[str] = []
    total_chars = 0
    is_truncated = False
    chunk_size = 8192

    try:
        while True:
            remaining = max_chars - total_chars
            if remaining <= 0:
                is_truncated = True
                break
            # Read at most chunk_size bytes or remaining budget
            read_size = min(chunk_size, max(remaining * 4, chunk_size))
            raw_chunk = proc.stdout.read(read_size)
            if not raw_chunk:
                break
            decoded = raw_chunk.decode(encoding, errors="replace")
            if total_chars + len(decoded) > max_chars:
                allowed = max_chars - total_chars
                output_chunks.append(decoded[:allowed])
                total_chars += allowed
                is_truncated = True
                break
            output_chunks.append(decoded)
            total_chars += len(decoded)
    finally:
        if is_truncated:
            # Terminate subprocess early to prevent further memory and CPU consumption
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            except OSError:
                pass
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
        else:
            _, stderr_data = proc.communicate()
            if proc.returncode != 0:
                err_text = stderr_data.decode(encoding, errors="replace")
                raise DiffExtractionError(
                    f"git {' '.join(cmd)} exited with code {proc.returncode}: {err_text}"
                )

    return "".join(output_chunks), is_truncated


def is_binary_file(file_path: Path) -> bool:
    """Check if a file appears to be binary by looking for null bytes in initial chunk.

    Never follows symbolic links.
    """
    try:
        if file_path.is_symlink() or os.path.islink(file_path):
            return False
    except OSError:
        return False

    if not file_path.is_file():
        return False
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return False


def get_unstaged_diff(path: Optional[str] = None, max_size: Optional[int] = None) -> str:
    """Extract unstaged diff in the working tree."""
    root = get_repository_root(path)
    limit = max_size if max_size is not None else get_settings().max_diff_size
    diff_text, _ = _run_git_diff_bounded(
        ["diff", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=root,
        max_chars=limit,
    )
    return diff_text


def get_staged_diff(path: Optional[str] = None, max_size: Optional[int] = None) -> str:
    """Extract staged diff in the Git index."""
    root = get_repository_root(path)
    limit = max_size if max_size is not None else get_settings().max_diff_size
    diff_text, _ = _run_git_diff_bounded(
        ["diff", "--cached", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=root,
        max_chars=limit,
    )
    return diff_text


def get_combined_tracked_diff(path: Optional[str] = None, max_size: Optional[int] = None) -> str:
    """Extract combined tracked diff relative to HEAD (or fallback to staged if no HEAD)."""
    root = get_repository_root(path)
    limit = max_size if max_size is not None else get_settings().max_diff_size
    head_commit = get_current_commit(root)
    if not head_commit:
        # Initial repository without commits: diff relative to empty tree (cached diff)
        return get_staged_diff(root, max_size=limit)

    diff_text, _ = _run_git_diff_bounded(
        ["diff", "HEAD", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=root,
        max_chars=limit,
    )
    return diff_text


def generate_untracked_diff(
    untracked_relative_paths: List[str],
    root_path: Path,
    max_size: int = 100000,
    current_size: int = 0,
) -> Tuple[str, bool]:
    """Generate synthetic unified diffs for untracked files without modifying index or working tree.

    Never reads target file contents of untracked symlinks.
    Enforces memory-bounded reading on large untracked files.

    Returns:
        Tuple of (diff_content, is_truncated).
    """
    diff_blocks: List[str] = []
    accumulated_size = current_size
    truncated = False

    for rel_path in untracked_relative_paths:
        full_path = root_path / rel_path

        # Security: detect every symlink (internal, external, directory, or broken)
        # Never call is_file(), is_binary_file(), or open() on a symlink.
        if full_path.is_symlink() or os.path.islink(full_path):
            try:
                target = os.readlink(full_path)
            except OSError:
                continue
            norm_rel = rel_path.replace("\\", "/")
            target_str = str(target).replace("\\", "/")
            block = (
                f"diff --git a/{norm_rel} b/{norm_rel}\n"
                f"new file mode 120000\n"
                f"--- /dev/null\n"
                f"+++ b/{norm_rel}\n"
                f"@@ -0,0 +1 @@\n"
                f"+symbolic link -> {target_str}\n"
            )
            if accumulated_size + len(block) > max_size:
                truncated = True
                break
            diff_blocks.append(block)
            accumulated_size += len(block)
            continue

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

        # Memory-bounded file reading: do not read more than remaining budget
        remaining_budget = max_size - accumulated_size
        if remaining_budget <= 0:
            truncated = True
            break

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(remaining_budget + 1)
        except (OSError, PermissionError):
            continue

        if len(content) > remaining_budget:
            truncated = True
            break

        lines = content.splitlines(keepends=True)
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
            truncated = True
            break

        diff_blocks.append(block)
        accumulated_size += len(block)

    return "".join(diff_blocks), truncated


def extract_all_diffs(
    path: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> ExtractedDiffs:
    """Extract staged, unstaged, and untracked diffs with memory-bounded streaming."""
    cfg = settings or get_settings()
    max_size = cfg.max_diff_size
    root = Path(get_repository_root(path))
    is_truncated = False

    # 1. Extract unstaged diff with bounded streaming
    unstaged, unstaged_trunc = _run_git_diff_bounded(
        ["diff", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=str(root),
        max_chars=max_size,
    )
    if unstaged_trunc:
        return ExtractedDiffs(
            unstaged_diff=unstaged,
            staged_diff="",
            combined_diff="",
            untracked_diff="",
            is_truncated=True,
        )

    # 2. Extract staged diff with bounded streaming
    remaining_budget = max_size - len(unstaged)
    if remaining_budget <= 0:
        return ExtractedDiffs(
            unstaged_diff=unstaged,
            staged_diff="",
            combined_diff="",
            untracked_diff="",
            is_truncated=True,
        )

    staged, staged_trunc = _run_git_diff_bounded(
        ["diff", "--cached", "--no-ext-diff", "--no-color", "--no-renames"],
        cwd=str(root),
        max_chars=remaining_budget,
    )
    if staged_trunc:
        return ExtractedDiffs(
            unstaged_diff=unstaged,
            staged_diff=staged,
            combined_diff="",
            untracked_diff="",
            is_truncated=True,
        )

    # 3. Avoid retrieving a second full combined diff unnecessarily
    if not unstaged and not staged:
        combined = ""
    elif staged and not unstaged:
        combined = staged
    elif unstaged and not staged:
        combined = unstaged
    else:
        # Both staged and unstaged changes exist: bounded read of diff HEAD
        head_commit = get_current_commit(root)
        if head_commit:
            combined, _ = _run_git_diff_bounded(
                ["diff", "HEAD", "--no-ext-diff", "--no-color", "--no-renames"],
                cwd=str(root),
                max_chars=max_size,
            )
        else:
            combined = staged

    # 4. Extract untracked files with remaining budget
    total_tracked_len = len(unstaged) + len(staged)
    untracked_budget = max_size - total_tracked_len

    if untracked_budget <= 0:
        is_truncated = True
        untracked = ""
    else:
        # Retrieve untracked files safely from git status
        proc_status = _run_git_command(
            ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=str(root),
            check=True,
        )
        status_changes = parse_porcelain_status(proc_status.stdout)
        untracked_paths = [c.file_path for c in status_changes if c.is_untracked]

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
