"""Pytest fixtures for Git engine testing with isolated temporary repositories."""

import subprocess
from pathlib import Path
import pytest


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create an empty initialized Git repository in a temporary directory."""
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Developer"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "developer@example.com"], cwd=str(repo), check=True, capture_output=True)

    return repo


@pytest.fixture
def repo_with_initial_commit(temp_git_repo: Path) -> Path:
    """Create a temporary Git repository with an initial commit."""
    readme = temp_git_repo / "README.md"
    readme.write_text("# Test Repo\nInitial content\n", encoding="utf-8")

    subprocess.run(["git", "add", "README.md"], cwd=str(temp_git_repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(temp_git_repo), check=True, capture_output=True)

    return temp_git_repo
