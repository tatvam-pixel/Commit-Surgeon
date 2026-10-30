"""Tests for git_engine/repository.py - repository detection and metadata."""

import subprocess
from pathlib import Path
import pytest

from git_engine.exceptions import (
    GitError,
    InvalidRepositoryPathError,
    NotAGitRepositoryError,
)
from git_engine.repository import (
    get_current_branch,
    get_current_commit,
    get_git_version,
    get_repository_info,
    get_repository_root,
    is_detached_head,
    is_git_repository,
)


class TestIsGitRepository:
    def test_valid_repository(self, repo_with_initial_commit: Path):
        assert is_git_repository(str(repo_with_initial_commit)) is True

    def test_invalid_directory(self, tmp_path: Path):
        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()
        assert is_git_repository(str(non_repo)) is False

    def test_empty_repo_without_commits(self, temp_git_repo: Path):
        assert is_git_repository(str(temp_git_repo)) is True

    def test_nonexistent_path(self, tmp_path: Path):
        assert is_git_repository(str(tmp_path / "does_not_exist")) is False


class TestGetRepositoryRoot:
    def test_root_from_repo_root(self, repo_with_initial_commit: Path):
        root = get_repository_root(str(repo_with_initial_commit))
        assert Path(root).is_dir()
        assert Path(root).name == repo_with_initial_commit.name

    def test_root_from_subdirectory(self, repo_with_initial_commit: Path):
        subdir = repo_with_initial_commit / "src"
        subdir.mkdir()
        root = get_repository_root(str(subdir))
        assert Path(root).resolve() == repo_with_initial_commit.resolve()

    def test_raises_for_non_repo(self, tmp_path: Path):
        non_repo = tmp_path / "plain_dir"
        non_repo.mkdir()
        with pytest.raises(NotAGitRepositoryError):
            get_repository_root(str(non_repo))

    def test_raises_for_missing_path(self, tmp_path: Path):
        with pytest.raises((InvalidRepositoryPathError, NotAGitRepositoryError)):
            get_repository_root(str(tmp_path / "ghost"))


class TestGetGitVersion:
    def test_returns_version_string(self):
        version = get_git_version()
        assert "git" in version.lower() or version == "unknown"


class TestGetCurrentBranch:
    def test_branch_after_initial_commit(self, repo_with_initial_commit: Path):
        branch = get_current_branch(str(repo_with_initial_commit))
        assert branch is not None
        assert isinstance(branch, str)
        assert len(branch) > 0

    def test_empty_repo_returns_none_or_string(self, temp_git_repo: Path):
        # Unborn branch: git >= 2.28 shows main/master, older returns None
        branch = get_current_branch(str(temp_git_repo))
        # Either None or a string is acceptable
        assert branch is None or isinstance(branch, str)


class TestGetCurrentCommit:
    def test_commit_after_initial(self, repo_with_initial_commit: Path):
        commit = get_current_commit(str(repo_with_initial_commit))
        assert commit is not None
        assert len(commit) == 40  # Full SHA-1

    def test_no_commit_returns_none(self, temp_git_repo: Path):
        commit = get_current_commit(str(temp_git_repo))
        assert commit is None


class TestIsDetachedHead:
    def test_not_detached_on_normal_branch(self, repo_with_initial_commit: Path):
        assert is_detached_head(str(repo_with_initial_commit)) is False

    def test_detached_head(self, repo_with_initial_commit: Path):
        commit = get_current_commit(str(repo_with_initial_commit))
        subprocess.run(
            ["git", "checkout", "--detach", commit],
            cwd=str(repo_with_initial_commit),
            check=True,
            capture_output=True,
        )
        assert is_detached_head(str(repo_with_initial_commit)) is True

    def test_empty_repo_not_detached(self, temp_git_repo: Path):
        assert is_detached_head(str(temp_git_repo)) is False


class TestGetRepositoryInfo:
    def test_full_info_populated(self, repo_with_initial_commit: Path):
        info = get_repository_info(str(repo_with_initial_commit))
        assert info.root_path != ""
        assert info.current_branch is not None
        assert info.current_commit is not None
        assert len(info.current_commit) == 40
        assert "git version" in info.git_version.lower()
        assert info.is_detached is False

    def test_raises_for_non_repo(self, tmp_path: Path):
        non_repo = tmp_path / "not_git"
        non_repo.mkdir()
        with pytest.raises(NotAGitRepositoryError):
            get_repository_info(str(non_repo))

    def test_raises_for_missing_path(self, tmp_path: Path):
        with pytest.raises((InvalidRepositoryPathError, NotAGitRepositoryError)):
            get_repository_info(str(tmp_path / "missing"))

    def test_empty_repo_no_commit(self, temp_git_repo: Path):
        info = get_repository_info(str(temp_git_repo))
        assert info.current_commit is None
        assert info.is_detached is False
