"""Pydantic models for structured Git repository change representation."""

from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class DiffHunk(BaseModel):
    """Represents a single unified diff hunk."""

    hunk_id: str = Field(description="Unique identifier for the hunk")
    source_state: str = Field(
        default="unstaged",
        description="Source state of the hunk: 'staged', 'unstaged', or 'untracked'",
    )
    old_start: int = Field(default=0, description="Starting line in original file")
    old_count: int = Field(default=0, description="Number of lines in original file")
    new_start: int = Field(default=0, description="Starting line in new file")
    new_count: int = Field(default=0, description="Number of lines in new file")
    header: str = Field(default="", description="Unified diff hunk header (@@ ... @@)")
    content: str = Field(default="", description="Full content of the hunk including diff prefixes")
    added_lines: int = Field(default=0, description="Number of added lines in this hunk")
    deleted_lines: int = Field(default=0, description="Number of deleted lines in this hunk")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }

    @property
    def source(self) -> str:
        """Alias for source_state."""
        return self.source_state

    @property
    def is_staged(self) -> bool:
        """True if hunk comes from staged index changes."""
        return self.source_state == "staged"

    @property
    def is_unstaged(self) -> bool:
        """True if hunk comes from unstaged working tree changes."""
        return self.source_state == "unstaged"

    @property
    def is_untracked(self) -> bool:
        """True if hunk comes from untracked file."""
        return self.source_state == "untracked"


class FileChange(BaseModel):
    """Represents changes detected in a single file."""

    file_path: str = Field(description="Path to the file relative to repository root")
    old_path: Optional[str] = Field(default=None, description="Original file path if renamed or copied")
    new_path: Optional[str] = Field(default=None, description="New file path if renamed or copied")
    change_type: str = Field(
        default="modified",
        description="Type of change: modified, added, deleted, renamed, copied, untracked, conflicted",
    )
    is_staged: bool = Field(default=False, description="Whether change is in Git index (staged)")
    is_unstaged: bool = Field(default=False, description="Whether change is in working tree (unstaged)")
    is_untracked: bool = Field(default=False, description="Whether file is untracked by Git")
    is_binary: bool = Field(default=False, description="Whether file is identified as binary")
    added_lines: int = Field(default=0, description="Total added lines in this file change")
    deleted_lines: int = Field(default=0, description="Total deleted lines in this file change")
    staged_added_lines: int = Field(default=0, description="Total added lines in staged hunks")
    staged_deleted_lines: int = Field(default=0, description="Total deleted lines in staged hunks")
    unstaged_added_lines: int = Field(default=0, description="Total added lines in unstaged hunks")
    unstaged_deleted_lines: int = Field(default=0, description="Total deleted lines in unstaged hunks")
    hunks: List[DiffHunk] = Field(default_factory=list, description="Parsed diff hunks for this file")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }

    @property
    def staged_hunks(self) -> List[DiffHunk]:
        """List of hunks from staged changes."""
        return [h for h in self.hunks if h.is_staged]

    @property
    def unstaged_hunks(self) -> List[DiffHunk]:
        """List of hunks from unstaged or untracked changes."""
        return [h for h in self.hunks if not h.is_staged]

    @model_validator(mode="after")
    def compute_hunk_stats_if_unset(self):
        """Automatically calculate line stats from hunks if unset."""
        if self.hunks:
            if self.staged_added_lines == 0 and any(h.is_staged for h in self.hunks):
                self.staged_added_lines = sum(h.added_lines for h in self.hunks if h.is_staged)
            if self.staged_deleted_lines == 0 and any(h.is_staged for h in self.hunks):
                self.staged_deleted_lines = sum(h.deleted_lines for h in self.hunks if h.is_staged)
            if self.unstaged_added_lines == 0 and any(not h.is_staged for h in self.hunks):
                self.unstaged_added_lines = sum(h.added_lines for h in self.hunks if not h.is_staged)
            if self.unstaged_deleted_lines == 0 and any(not h.is_staged for h in self.hunks):
                self.unstaged_deleted_lines = sum(h.deleted_lines for h in self.hunks if not h.is_staged)
        return self


class RepositoryInfo(BaseModel):
    """Metadata describing a Git repository."""

    root_path: str = Field(description="Absolute path to repository root")
    current_branch: Optional[str] = Field(default=None, description="Name of current active branch")
    current_commit: Optional[str] = Field(default=None, description="HEAD commit SHA-1 or None if empty")
    git_version: str = Field(default="unknown", description="Installed Git version string")
    is_detached: bool = Field(default=False, description="True if HEAD is in detached state")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }


class RepositoryChanges(BaseModel):
    """Consolidated report of changes across the working tree and index."""

    repository: RepositoryInfo = Field(description="Repository metadata")
    changes: List[FileChange] = Field(default_factory=list, description="List of file changes")
    total_files: int = Field(default=0, description="Total number of changed files")
    total_added_lines: int = Field(default=0, description="Total added lines across all hunks")
    total_deleted_lines: int = Field(default=0, description="Total deleted lines across all hunks")
    total_hunks: int = Field(default=0, description="Total diff hunks parsed")
    staged_added_lines: int = Field(default=0, description="Total added lines across staged hunks")
    staged_deleted_lines: int = Field(default=0, description="Total deleted lines across staged hunks")
    unstaged_added_lines: int = Field(default=0, description="Total added lines across unstaged hunks")
    unstaged_deleted_lines: int = Field(default=0, description="Total deleted lines across unstaged hunks")
    staged_hunks: int = Field(default=0, description="Total staged diff hunks")
    unstaged_hunks: int = Field(default=0, description="Total unstaged diff hunks")
    has_conflicts: bool = Field(default=False, description="True if unresolved merge conflicts exist")
    has_truncated_content: bool = Field(
        default=False,
        description="True if diff extraction was truncated due to max size limits",
    )

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }

    @property
    def staged_hunk_count(self) -> int:
        """Alias for staged_hunks count."""
        return self.staged_hunks

    @property
    def unstaged_hunk_count(self) -> int:
        """Alias for unstaged_hunks count."""
        return self.unstaged_hunks

    def get_staged_hunks(self) -> List[DiffHunk]:
        """Retrieve all staged DiffHunks across all file changes."""
        result: List[DiffHunk] = []
        for change in self.changes:
            result.extend(change.staged_hunks)
        return result

    def get_unstaged_hunks(self) -> List[DiffHunk]:
        """Retrieve all unstaged and untracked DiffHunks across all file changes."""
        result: List[DiffHunk] = []
        for change in self.changes:
            result.extend(change.unstaged_hunks)
        return result

    @property
    def modified_count(self) -> int:
        """Count of modified files."""
        return sum(1 for c in self.changes if c.change_type == "modified")

    @property
    def added_count(self) -> int:
        """Count of added files."""
        return sum(1 for c in self.changes if c.change_type == "added")

    @property
    def deleted_count(self) -> int:
        """Count of deleted files."""
        return sum(1 for c in self.changes if c.change_type == "deleted")

    @property
    def renamed_count(self) -> int:
        """Count of renamed files."""
        return sum(1 for c in self.changes if c.change_type == "renamed")

    @property
    def untracked_count(self) -> int:
        """Count of untracked files."""
        return sum(1 for c in self.changes if c.is_untracked or c.change_type == "untracked")

    @property
    def conflicted_count(self) -> int:
        """Count of conflicted files."""
        return sum(1 for c in self.changes if c.change_type == "conflicted")

    @model_validator(mode="after")
    def compute_defaults_if_unset(self):
        """Automatically calculate summary stats from changes if unset."""
        if self.changes:
            if self.staged_added_lines == 0 and any(h.is_staged for c in self.changes for h in c.hunks):
                self.staged_added_lines = sum(c.staged_added_lines for c in self.changes)
            if self.staged_deleted_lines == 0 and any(h.is_staged for c in self.changes for h in c.hunks):
                self.staged_deleted_lines = sum(c.staged_deleted_lines for c in self.changes)
            if self.unstaged_added_lines == 0 and any(not h.is_staged for c in self.changes for h in c.hunks):
                self.unstaged_added_lines = sum(c.unstaged_added_lines for c in self.changes)
            if self.unstaged_deleted_lines == 0 and any(not h.is_staged for c in self.changes for h in c.hunks):
                self.unstaged_deleted_lines = sum(c.unstaged_deleted_lines for c in self.changes)
            if self.staged_hunks == 0:
                self.staged_hunks = sum(len(c.staged_hunks) for c in self.changes)
            if self.unstaged_hunks == 0:
                self.unstaged_hunks = sum(len(c.unstaged_hunks) for c in self.changes)
        return self
