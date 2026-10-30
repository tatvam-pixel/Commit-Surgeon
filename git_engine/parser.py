"""Unified Git diff parser for hunk extraction and structured representation."""

import re
from typing import Dict, List, Optional, Tuple

from git_engine.exceptions import DiffParsingError
from git_engine.models import DiffHunk, FileChange

HUNK_HEADER_REGEX = re.compile(
    r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$"
)


def parse_hunk_header(header_line: str) -> Tuple[int, int, int, int]:
    """Parse unified diff hunk header into (old_start, old_count, new_start, new_count).

    Example:
        @@ -10,3 +10,5 @@ -> (10, 3, 10, 5)
        @@ -1 +1,2 @@   -> (1, 1, 1, 2)
        @@ -0,0 +1,5 @@ -> (0, 0, 1, 5)
    """
    match = HUNK_HEADER_REGEX.match(header_line.strip())
    if not match:
        raise DiffParsingError(f"Invalid hunk header format: {header_line}")

    old_start_str, old_count_str, new_start_str, new_count_str, _ = match.groups()

    old_start = int(old_start_str)
    new_start = int(new_start_str)

    # In unified diff, if count is omitted, it defaults to 1, unless start is 0
    if old_count_str is not None:
        old_count = int(old_count_str)
    else:
        old_count = 0 if old_start == 0 else 1

    if new_count_str is not None:
        new_count = int(new_count_str)
    else:
        new_count = 0 if new_start == 0 else 1

    return old_start, old_count, new_start, new_count


def _extract_file_paths_from_diff_git(line: str) -> Tuple[str, str]:
    """Extract old and new paths from a 'diff --git a/... b/...' line."""
    # Standard format: diff --git a/<old> b/<new>
    prefix = "diff --git "
    if not line.startswith(prefix):
        raise DiffParsingError(f"Expected 'diff --git', got: {line}")

    rest = line[len(prefix):]
    # Find split point between a/ and b/
    # If filename has spaces, ' b/' could appear in the middle, so we find ' b/' matching
    # Best heuristic: if line contains ' b/', check candidate splits
    if " a/" in rest or rest.startswith("a/"):
        # standard case
        if rest.startswith("a/"):
            rest_no_a = rest[2:]
            # We look for ' b/'
            parts = rest_no_a.split(" b/")
            if len(parts) == 2:
                return parts[0], parts[1]
            elif len(parts) > 2:
                # Handle filename containing ' b/' by joining halves
                # Or fallback to splitting at half
                mid = len(parts) // 2
                return " b/".join(parts[:mid]), " b/".join(parts[mid:])

    # Fallback: simple split
    parts = rest.split()
    if len(parts) >= 2:
        old = parts[0][2:] if parts[0].startswith("a/") else parts[0]
        new = parts[1][2:] if parts[1].startswith("b/") else parts[1]
        return old, new

    return rest, rest


def parse_unified_diff(
    diff_text: str,
    source_state: str = "unstaged",
) -> List[FileChange]:
    """Parse complete unified diff text into a list of FileChange models with DiffHunk objects."""
    if not diff_text or not diff_text.strip():
        return []

    lines = diff_text.splitlines(keepends=True)
    file_changes: List[FileChange] = []

    # Partition lines into file blocks based on 'diff --git'
    file_blocks: List[List[str]] = []
    current_block: List[str] = []

    for line in lines:
        if line.startswith("diff --git "):
            if current_block:
                file_blocks.append(current_block)
            current_block = [line]
        else:
            if current_block:
                current_block.append(line)
            else:
                # Diff text starts without 'diff --git ' (e.g. raw single hunk or patch)
                current_block = [line]

    if current_block:
        file_blocks.append(current_block)

    hunk_counter = 0

    for block in file_blocks:
        first_line = block[0].strip()
        old_path: Optional[str] = None
        new_path: Optional[str] = None
        file_path: str = ""
        change_type = "modified"
        is_binary = False

        if first_line.startswith("diff --git "):
            old_p, new_p = _extract_file_paths_from_diff_git(first_line)
            old_path = old_p
            new_path = new_p
            file_path = new_p
        else:
            file_path = "unknown"

        # Scan file header lines before hunks
        hunk_start_idx = -1
        for idx, line in enumerate(block):
            s_line = line.strip()
            if s_line.startswith("new file mode "):
                change_type = "added"
            elif s_line.startswith("deleted file mode "):
                change_type = "deleted"
            elif s_line.startswith("similarity index "):
                change_type = "renamed"
            elif s_line.startswith("rename from "):
                old_path = s_line[len("rename from "):].strip()
                change_type = "renamed"
            elif s_line.startswith("rename to "):
                new_path = s_line[len("rename to "):].strip()
                file_path = new_path
                change_type = "renamed"
            elif s_line.startswith("copy from "):
                old_path = s_line[len("copy from "):].strip()
                change_type = "copied"
            elif s_line.startswith("copy to "):
                new_path = s_line[len("copy to "):].strip()
                file_path = new_path
                change_type = "copied"
            elif s_line.startswith("Binary files ") and " differ" in s_line:
                is_binary = True
            elif s_line.startswith("GIT binary patch"):
                is_binary = True
            elif s_line.startswith("--- "):
                path_part = s_line[4:].strip()
                if path_part == "/dev/null":
                    change_type = "added"
                elif path_part.startswith("a/"):
                    old_path = path_part[2:]
            elif s_line.startswith("+++ "):
                path_part = s_line[4:].strip()
                if path_part == "/dev/null":
                    change_type = "deleted"
                elif path_part.startswith("b/"):
                    new_path = path_part[2:]
                    file_path = new_path
            elif s_line.startswith("@@ "):
                hunk_start_idx = idx
                break

        hunks: List[DiffHunk] = []
        file_added = 0
        file_deleted = 0

        if hunk_start_idx != -1:
            # Group lines into hunks
            hunk_lines_list: List[List[str]] = []
            curr_hunk_lines: List[str] = []

            for line in block[hunk_start_idx:]:
                if line.startswith("@@ "):
                    if curr_hunk_lines:
                        hunk_lines_list.append(curr_hunk_lines)
                    curr_hunk_lines = [line]
                else:
                    if curr_hunk_lines:
                        curr_hunk_lines.append(line)

            if curr_hunk_lines:
                hunk_lines_list.append(curr_hunk_lines)

            for h_lines in hunk_lines_list:
                header = h_lines[0].strip()
                try:
                    old_s, old_c, new_s, new_c = parse_hunk_header(header)
                except DiffParsingError:
                    # If malformed header, record default values
                    old_s, old_c, new_s, new_c = 0, 0, 0, 0

                hunk_added = 0
                hunk_deleted = 0
                for body_line in h_lines[1:]:
                    if body_line.startswith("+"):
                        hunk_added += 1
                    elif body_line.startswith("-"):
                        hunk_deleted += 1

                file_added += hunk_added
                file_deleted += hunk_deleted
                hunk_counter += 1

                hunk_id = f"hunk_{hunk_counter}_{source_state}_{file_path.replace('/', '_')}"
                hunks.append(
                    DiffHunk(
                        hunk_id=hunk_id,
                        source_state=source_state,
                        old_start=old_s,
                        old_count=old_c,
                        new_start=new_s,
                        new_count=new_c,
                        header=header,
                        content="".join(h_lines),
                        added_lines=hunk_added,
                        deleted_lines=hunk_deleted,
                    )
                )

        is_staged = source_state == "staged"
        is_unstaged = source_state in ("unstaged", "untracked")
        is_untracked = source_state == "untracked"

        file_changes.append(
            FileChange(
                file_path=file_path or (new_path or (old_path or "unknown")),
                old_path=old_path,
                new_path=new_path,
                change_type=change_type,
                is_staged=is_staged,
                is_unstaged=is_unstaged,
                is_untracked=is_untracked,
                is_binary=is_binary,
                added_lines=file_added,
                deleted_lines=file_deleted,
                staged_added_lines=file_added if is_staged else 0,
                staged_deleted_lines=file_deleted if is_staged else 0,
                unstaged_added_lines=file_added if is_unstaged else 0,
                unstaged_deleted_lines=file_deleted if is_unstaged else 0,
                hunks=hunks,
            )
        )

    return file_changes
