"""Exceptions for Git engine operations."""

from typing import Optional, List


class GitError(Exception):
    """Base exception for all Git engine errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotAGitRepositoryError(GitError):
    """Raised when an operation targets a directory that is not a Git repository."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Directory is not a Git repository: {path}")
        self.path = path


class GitExecutableNotFoundError(GitError):
    """Raised when the git executable cannot be located in the system PATH."""

    def __init__(self) -> None:
        super().__init__("Git executable 'git' not found in system PATH.")


class InvalidRepositoryPathError(GitError):
    """Raised when the specified repository path does not exist or is not a directory."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Invalid repository path: {path}")
        self.path = path


class GitCommandError(GitError):
    """Raised when a Git subprocess command exits with a non-zero status."""

    def __init__(
        self,
        command: List[str],
        returncode: int,
        stderr: str,
        stdout: Optional[str] = None,
    ) -> None:
        cmd_str = " ".join(command)
        err_msg = stderr.strip() if stderr else f"exit code {returncode}"
        super().__init__(f"Git command failed ({cmd_str}): {err_msg}")
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


class DiffExtractionError(GitError):
    """Raised when Git diff extraction fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Failed to extract Git diff: {reason}")
        self.reason = reason


class DiffParsingError(GitError):
    """Raised when diff output cannot be parsed into hunks or file changes."""

    def __init__(self, reason: str, line_num: Optional[int] = None) -> None:
        loc = f" at line {line_num}" if line_num is not None else ""
        super().__init__(f"Diff parsing error{loc}: {reason}")
        self.reason = reason
        self.line_num = line_num


class UnavailableHeadError(GitError):
    """Raised when HEAD commit cannot be referenced (e.g. empty repository without commits)."""

    def __init__(self, repo_path: str) -> None:
        super().__init__(f"Repository has no commits or HEAD is unavailable: {repo_path}")
        self.repo_path = repo_path


class MergeConflictError(GitError):
    """Raised when the repository contains unresolved merge conflicts."""

    def __init__(self, conflicted_files: List[str]) -> None:
        files_str = ", ".join(conflicted_files)
        super().__init__(f"Repository has unresolved merge conflicts in: {files_str}")
        self.conflicted_files = conflicted_files


class OversizedDiffError(GitError):
    """Raised when a diff exceeds the configured maximum allowed size."""

    def __init__(self, size: int, max_size: int) -> None:
        super().__init__(
            f"Diff size ({size} characters) exceeds configured maximum ({max_size} characters)."
        )
        self.size = size
        self.max_size = max_size
