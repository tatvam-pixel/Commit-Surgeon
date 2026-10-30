"""Git engine package for Commit Surgeon repository operations."""

from git_engine.analyzer import analyze_repository
from git_engine.diff import (
    ExtractedDiffs,
    extract_all_diffs,
    get_combined_tracked_diff,
    get_staged_diff,
    get_unstaged_diff,
)
from git_engine.exceptions import (
    DiffExtractionError,
    DiffParsingError,
    GitCommandError,
    GitError,
    GitExecutableNotFoundError,
    InvalidRepositoryPathError,
    MergeConflictError,
    NotAGitRepositoryError,
    OversizedDiffError,
    UnavailableHeadError,
)
from git_engine.models import (
    DiffHunk,
    FileChange,
    RepositoryChanges,
    RepositoryInfo,
)
from git_engine.parser import parse_hunk_header, parse_unified_diff
from git_engine.repository import (
    get_current_branch,
    get_current_commit,
    get_git_version,
    get_repository_info,
    get_repository_root,
    is_detached_head,
    is_git_repository,
)
from git_engine.status import (
    get_conflicted_files,
    get_repository_status,
    get_staged_changes,
    get_unstaged_changes,
    get_untracked_files,
    parse_porcelain_status,
)

__all__ = [
    # Coordinator
    "analyze_repository",
    # Models
    "DiffHunk",
    "FileChange",
    "RepositoryInfo",
    "RepositoryChanges",
    "ExtractedDiffs",
    # Exceptions
    "GitError",
    "NotAGitRepositoryError",
    "GitExecutableNotFoundError",
    "InvalidRepositoryPathError",
    "GitCommandError",
    "DiffExtractionError",
    "DiffParsingError",
    "UnavailableHeadError",
    "MergeConflictError",
    "OversizedDiffError",
    # Repository inspection
    "is_git_repository",
    "get_repository_root",
    "get_git_version",
    "get_current_branch",
    "get_current_commit",
    "is_detached_head",
    "get_repository_info",
    # Status
    "get_repository_status",
    "parse_porcelain_status",
    "get_staged_changes",
    "get_unstaged_changes",
    "get_untracked_files",
    "get_conflicted_files",
    # Diff
    "get_unstaged_diff",
    "get_staged_diff",
    "get_combined_tracked_diff",
    "extract_all_diffs",
    # Parser
    "parse_hunk_header",
    "parse_unified_diff",
]
