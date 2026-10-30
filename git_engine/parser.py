"""Unified Git diff parser for hunk extraction and structured representation."""

import hashlib
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


def _git_unquote(s: str) -> str:
    """Unescape Git C-style quoted path."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            c = s[i + 1]
            if c == "n":
                result.append("\n")
            elif c == "t":
                result.append("\t")
            elif c == "\\":
                result.append("\\")
            elif c == '"':
                result.append('"')
            elif c.isdigit():
                # Octal escape: \OOO represents raw byte
                octal = c
                for k in range(2):
                    if i + 2 + k < len(s) and s[i + 2 + k].isdigit():
                        octal += s[i + 2 + k]
                    else:
                        break
                byte_val = int(octal, 8)
                result.append(chr(byte_val))
                i += 1 + len(octal)
                continue
            else:
                result.append(c)
            i += 2
        else:
            result.append(s[i])
            i += 1
    raw_str = "".join(result)
    # If the unquoted string contains multi-byte UTF-8 encoded as raw latin1 chars, decode it
    try:
        raw_bytes = raw_str.encode("latin-1")
        return raw_bytes.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw_str


def _clean_git_header_path(raw: str, prefix: Optional[str] = None) -> str:
    """Clean, unescape, and strip prefixes from a path in a Git diff header."""
    p = raw.strip()
    if p.startswith('"') and p.endswith('"'):
        p = _git_unquote(p[1:-1])
    elif '"' in p:
        p = _git_unquote(p)

    if prefix and p.startswith(prefix):
        p = p[len(prefix):]
    elif p.startswith("a/") or p.startswith("b/"):
        p = p[2:]

    # Also handle if prefix was inside quotes (e.g. "a/foo" -> unquoted a/foo -> foo)
    if prefix and p.startswith(prefix):
        p = p[len(prefix):]
    elif p.startswith("a/") or p.startswith("b/"):
        p = p[2:]

    return p.replace("\\", "/")


def _split_quoted_paths(rest: str) -> Optional[Tuple[str, str]]:
    """Parse Git quoted path format: \"a/path\" \"b/path\" or mixed."""
    try:
        parts = []
        i = 0
        while i < len(rest):
            if rest[i] == '"':
                j = i + 1
                while j < len(rest):
                    if rest[j] == "\\" and j + 1 < len(rest):
                        j += 2
                        continue
                    if rest[j] == '"':
                        break
                    j += 1
                quoted = rest[i + 1 : j]
                quoted = _clean_git_header_path(quoted)
                parts.append(quoted)
                i = j + 1
            elif rest[i] == " ":
                i += 1
            else:
                end = rest.find(" ", i)
                if end == -1:
                    parts.append(_clean_git_header_path(rest[i:]))
                    break
                parts.append(_clean_git_header_path(rest[i:end]))
                i = end

        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return None


def _extract_file_paths_from_diff_git(
    line: str,
    known_paths: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """Extract old and new paths from a 'diff --git a/... b/...' line without ambiguous splitting.

    Handles edge cases:
    - Authoritative matching against known repository paths when provided
    - Exact O(1) mathematical midpoint resolution for non-rename changes
    - Filenames containing ' b/' literally
    - Git quoted paths with C-style escapes
    - Unicode and unusual characters
    """
    prefix = "diff --git "
    if not line.startswith(prefix):
        raise DiffParsingError(f"Expected 'diff --git', got: {line}")

    rest = line[len(prefix):]

    # 1. Authoritative lookup: match directly against known repository paths if provided
    if known_paths:
        norm_paths = sorted([kp.replace("\\", "/") for kp in known_paths], key=len, reverse=True)
        for kp in norm_paths:
            if rest == f"a/{kp} b/{kp}" or rest == f'"{kp}" "{kp}"' or rest == f'"a/{kp}" "b/{kp}"':
                return kp, kp

    # 2. Handle Git quoted paths: "a/path" "b/path"
    if rest.startswith('"'):
        parts = _split_quoted_paths(rest)
        if parts:
            return parts

    # 3. Exact deterministic resolution for standard identical paths: a/<X> b/<X>
    # When old_path == new_path, the line format is "a/" + X + " b/" + X.
    # Total length is 2*len(X) + 5. The path length is deterministically (len(rest) - 5) // 2.
    if rest.startswith("a/") and len(rest) >= 5 and (len(rest) - 5) % 2 == 0:
        path_len = (len(rest) - 5) // 2
        candidate_old = rest[2 : 2 + path_len]
        separator = rest[2 + path_len : 2 + path_len + 3]
        candidate_new = rest[2 + path_len + 3 :]
        if separator == " b/" and candidate_old == candidate_new:
            return candidate_old, candidate_new

    # 4. Fallback for rename diff --git lines (supplemented by rename from/to headers in caller)
    if " b/" in rest:
        parts = rest.split(" b/", 1)
        old = parts[0][2:] if parts[0].startswith("a/") else parts[0]
        new = parts[1]
        return old, new

    parts = rest.split()
    if len(parts) >= 2:
        old = parts[0][2:] if parts[0].startswith("a/") else parts[0]
        new = parts[1][2:] if parts[1].startswith("b/") else parts[1]
        return old, new

    return rest, rest


def parse_unified_diff(
    diff_text: str,
    source_state: str = "unstaged",
    known_paths: Optional[List[str]] = None,
) -> List[FileChange]:
    """Parse complete unified diff text into a list of FileChange models with DiffHunk objects.

    Uses authoritative header lines (--- a/..., +++ b/..., rename to ..., copy to ...)
    and optional known repository path metadata to eliminate ambiguous path heuristics.
    """
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

        # Scan file header lines before hunks to extract authoritative paths
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
                old_path = _clean_git_header_path(s_line[len("rename from "):])
                change_type = "renamed"
            elif s_line.startswith("rename to "):
                new_path = _clean_git_header_path(s_line[len("rename to "):])
                file_path = new_path
                change_type = "renamed"
            elif s_line.startswith("copy from "):
                old_path = _clean_git_header_path(s_line[len("copy from "):])
                change_type = "copied"
            elif s_line.startswith("copy to "):
                new_path = _clean_git_header_path(s_line[len("copy to "):])
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
                else:
                    old_path = _clean_git_header_path(path_part, prefix="a/")
            elif s_line.startswith("+++ "):
                path_part = s_line[4:].strip()
                if path_part == "/dev/null":
                    change_type = "deleted"
                else:
                    new_path = _clean_git_header_path(path_part, prefix="b/")
                    file_path = new_path
            elif s_line.startswith("@@ "):
                hunk_start_idx = idx
                break

        # Fallback to diff --git line if paths were not resolved from ---/+++/rename headers
        if not file_path or not old_path or not new_path:
            if first_line.startswith("diff --git "):
                old_p, new_p = _extract_file_paths_from_diff_git(first_line, known_paths=known_paths)
                if not old_path:
                    old_path = old_p
                if not new_path:
                    new_path = new_p
                if not file_path:
                    file_path = new_p or old_p
            else:
                if not file_path:
                    file_path = "unknown"

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

                path_hash = hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:12]
                hunk_id = f"hunk_{hunk_counter}_{source_state}_{path_hash}"
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
