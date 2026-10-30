"""Coordinator module for complete Git repository analysis."""

from pathlib import Path
from typing import Dict, List, Optional

from config.settings import Settings, get_settings
from git_engine.diff import extract_all_diffs
from git_engine.models import DiffHunk, FileChange, RepositoryChanges
from git_engine.parser import parse_unified_diff
from git_engine.repository import get_repository_info
from git_engine.status import get_repository_status


def analyze_repository(
    path: Optional[str] = None,
    settings: Optional[Settings] = None,
) -> RepositoryChanges:
    """Perform complete non-destructive analysis of repository changes.

    Collects repository metadata, working tree status, staged/unstaged diffs,
    and untracked files into a structured RepositoryChanges report.
    """
    cfg = settings or get_settings()
    repo_info = get_repository_info(path)
    root = repo_info.root_path

    # Step 1: Detect working tree and index status
    status_changes = get_repository_status(root)

    # Step 2: Extract staged, unstaged, and untracked diffs
    diffs = extract_all_diffs(root, settings=cfg)

    # Step 3: Parse unified diffs into hunks with authoritative path matching
    known_paths = [c.file_path for c in status_changes] + [
        c.old_path for c in status_changes if c.old_path
    ]
    staged_parsed = parse_unified_diff(
        diffs.staged_diff, source_state="staged", known_paths=known_paths
    )
    unstaged_parsed = parse_unified_diff(
        diffs.unstaged_diff, source_state="unstaged", known_paths=known_paths
    )
    untracked_parsed = parse_unified_diff(
        diffs.untracked_diff, source_state="untracked", known_paths=known_paths
    )

    # Index parsed changes by normalized file path
    parsed_by_path: Dict[str, List[FileChange]] = {}
    for p_change in staged_parsed + unstaged_parsed + untracked_parsed:
        norm = p_change.file_path.replace("\\", "/")
        if norm not in parsed_by_path:
            parsed_by_path[norm] = []
        parsed_by_path[norm].append(p_change)

    # Merge status with parsed diff hunks
    merged_changes: List[FileChange] = []
    seen_paths = set()

    for s_change in status_changes:
        norm_path = s_change.file_path.replace("\\", "/")
        seen_paths.add(norm_path)

        # Collect hunks and statistics from corresponding parsed diffs
        matching_parsed = parsed_by_path.get(norm_path, [])

        hunks: List[DiffHunk] = []
        added = 0
        deleted = 0
        is_bin = s_change.is_binary

        for mp in matching_parsed:
            hunks.extend(mp.hunks)
            added += mp.added_lines
            deleted += mp.deleted_lines
            if mp.is_binary:
                is_bin = True

        staged_added = sum(h.added_lines for h in hunks if h.is_staged)
        staged_deleted = sum(h.deleted_lines for h in hunks if h.is_staged)
        unstaged_added = sum(h.added_lines for h in hunks if not h.is_staged)
        unstaged_deleted = sum(h.deleted_lines for h in hunks if not h.is_staged)

        merged_changes.append(
            FileChange(
                file_path=s_change.file_path,
                old_path=s_change.old_path,
                new_path=s_change.new_path,
                change_type=s_change.change_type,
                is_staged=s_change.is_staged,
                is_unstaged=s_change.is_unstaged,
                is_untracked=s_change.is_untracked,
                is_binary=is_bin,
                added_lines=added,
                deleted_lines=deleted,
                staged_added_lines=staged_added,
                staged_deleted_lines=staged_deleted,
                unstaged_added_lines=unstaged_added,
                unstaged_deleted_lines=unstaged_deleted,
                hunks=hunks,
            )
        )

    # Add any parsed changes not captured in status (safety fallback)
    for norm_path, p_list in parsed_by_path.items():
        if norm_path not in seen_paths:
            seen_paths.add(norm_path)
            hunks = []
            added = 0
            deleted = 0
            is_bin = False
            first_change = p_list[0]
            for p in p_list:
                hunks.extend(p.hunks)
                added += p.added_lines
                deleted += p.deleted_lines
                if p.is_binary:
                    is_bin = True
            staged_added = sum(h.added_lines for h in hunks if h.is_staged)
            staged_deleted = sum(h.deleted_lines for h in hunks if h.is_staged)
            unstaged_added = sum(h.added_lines for h in hunks if not h.is_staged)
            unstaged_deleted = sum(h.deleted_lines for h in hunks if not h.is_staged)
            merged_changes.append(
                FileChange(
                    file_path=first_change.file_path,
                    old_path=first_change.old_path,
                    new_path=first_change.new_path,
                    change_type=first_change.change_type,
                    is_staged=first_change.is_staged,
                    is_unstaged=first_change.is_unstaged,
                    is_untracked=first_change.is_untracked,
                    is_binary=is_bin,
                    added_lines=added,
                    deleted_lines=deleted,
                    staged_added_lines=staged_added,
                    staged_deleted_lines=staged_deleted,
                    unstaged_added_lines=unstaged_added,
                    unstaged_deleted_lines=unstaged_deleted,
                    hunks=hunks,
                )
            )

    total_files = len(merged_changes)
    total_added = sum(c.added_lines for c in merged_changes)
    total_deleted = sum(c.deleted_lines for c in merged_changes)
    total_hunks = sum(len(c.hunks) for c in merged_changes)

    staged_added = sum(c.staged_added_lines for c in merged_changes)
    staged_deleted = sum(c.staged_deleted_lines for c in merged_changes)
    unstaged_added = sum(c.unstaged_added_lines for c in merged_changes)
    unstaged_deleted = sum(c.unstaged_deleted_lines for c in merged_changes)
    staged_hunks = sum(len(c.staged_hunks) for c in merged_changes)
    unstaged_hunks = sum(len(c.unstaged_hunks) for c in merged_changes)

    has_conflicts = any(c.change_type == "conflicted" for c in merged_changes)

    return RepositoryChanges(
        repository=repo_info,
        changes=merged_changes,
        total_files=total_files,
        total_added_lines=total_added,
        total_deleted_lines=total_deleted,
        total_hunks=total_hunks,
        staged_added_lines=staged_added,
        staged_deleted_lines=staged_deleted,
        unstaged_added_lines=unstaged_added,
        unstaged_deleted_lines=unstaged_deleted,
        staged_hunks=staged_hunks,
        unstaged_hunks=unstaged_hunks,
        has_conflicts=has_conflicts,
        has_truncated_content=diffs.is_truncated,
    )
