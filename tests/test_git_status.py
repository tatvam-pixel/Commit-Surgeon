"""Tests for git_engine/status.py - working tree and index status detection."""

import subprocess
from pathlib import Path
import pytest

from git_engine.status import (
    get_conflicted_files,
    get_repository_status,
    get_staged_changes,
    get_untracked_files,
    get_unstaged_changes,
    parse_porcelain_status,
)


class TestParsePorcelainStatus:
    def test_empty_output(self):
        assert parse_porcelain_status("") == []

    def test_modified_unstaged(self):
        output = " M src/main.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].file_path == "src/main.py"
        assert changes[0].change_type == "modified"
        assert changes[0].is_unstaged is True
        assert changes[0].is_staged is False

    def test_staged_new_file(self):
        output = "A  new_file.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].file_path == "new_file.py"
        assert changes[0].change_type == "added"
        assert changes[0].is_staged is True

    def test_untracked_file(self):
        output = "?? untracked.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].file_path == "untracked.py"
        assert changes[0].is_untracked is True
        assert changes[0].change_type == "untracked"

    def test_deleted_unstaged(self):
        output = " D deleted.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].change_type == "deleted"
        assert changes[0].is_unstaged is True

    def test_renamed_staged(self):
        # In -z format: "R  new.py\0old.py\0"
        output = "R  new.py\0old.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].change_type == "renamed"
        assert changes[0].file_path == "new.py"
        assert changes[0].old_path == "old.py"

    def test_conflicted_file_uu(self):
        output = "UU conflict.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].change_type == "conflicted"

    def test_conflicted_file_aa(self):
        output = "AA both_added.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].change_type == "conflicted"

    def test_filename_with_spaces(self):
        output = "?? my file with spaces.txt\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 1
        assert changes[0].file_path == "my file with spaces.txt"

    def test_multiple_entries(self):
        output = " M file1.py\0?? file2.txt\0A  file3.py\0"
        changes = parse_porcelain_status(output)
        assert len(changes) == 3


class TestGetRepositoryStatus:
    def test_clean_repo_no_changes(self, repo_with_initial_commit: Path):
        changes = get_repository_status(str(repo_with_initial_commit))
        assert changes == []

    def test_detects_modified_file(self, repo_with_initial_commit: Path):
        readme = repo_with_initial_commit / "README.md"
        readme.write_text("# Modified content\n", encoding="utf-8")
        changes = get_repository_status(str(repo_with_initial_commit))
        assert any(c.file_path == "README.md" and c.is_unstaged for c in changes)

    def test_detects_new_untracked_file(self, repo_with_initial_commit: Path):
        new_file = repo_with_initial_commit / "new_file.txt"
        new_file.write_text("new content", encoding="utf-8")
        changes = get_repository_status(str(repo_with_initial_commit))
        assert any(c.file_path == "new_file.txt" and c.is_untracked for c in changes)

    def test_detects_staged_file(self, repo_with_initial_commit: Path):
        new_file = repo_with_initial_commit / "staged.py"
        new_file.write_text("x = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "staged.py"],
            cwd=str(repo_with_initial_commit),
            check=True,
            capture_output=True,
        )
        changes = get_repository_status(str(repo_with_initial_commit))
        assert any(c.file_path == "staged.py" and c.is_staged for c in changes)

    def test_detects_deleted_file(self, repo_with_initial_commit: Path):
        readme = repo_with_initial_commit / "README.md"
        readme.unlink()
        changes = get_repository_status(str(repo_with_initial_commit))
        assert any(c.file_path == "README.md" and c.change_type == "deleted" for c in changes)

    def test_detects_renamed_file(self, repo_with_initial_commit: Path):
        subprocess.run(
            ["git", "mv", "README.md", "RENAMED.md"],
            cwd=str(repo_with_initial_commit),
            check=True,
            capture_output=True,
        )
        changes = get_repository_status(str(repo_with_initial_commit))
        assert any(c.change_type == "renamed" for c in changes)

    def test_filename_with_spaces(self, repo_with_initial_commit: Path):
        spaced = repo_with_initial_commit / "my file.txt"
        spaced.write_text("content", encoding="utf-8")
        changes = get_repository_status(str(repo_with_initial_commit))
        assert any("my file.txt" in c.file_path for c in changes)


class TestFilterHelpers:
    def test_get_staged_changes(self, repo_with_initial_commit: Path):
        (repo_with_initial_commit / "s.py").write_text("x=1\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "s.py"],
            cwd=str(repo_with_initial_commit),
            check=True,
            capture_output=True,
        )
        (repo_with_initial_commit / "u.py").write_text("y=2\n", encoding="utf-8")
        changes = get_repository_status(str(repo_with_initial_commit))
        staged = get_staged_changes(changes)
        assert all(c.is_staged for c in staged)
        assert any(c.file_path == "s.py" for c in staged)

    def test_get_unstaged_changes(self, repo_with_initial_commit: Path):
        readme = repo_with_initial_commit / "README.md"
        readme.write_text("# Changed\n", encoding="utf-8")
        changes = get_repository_status(str(repo_with_initial_commit))
        unstaged = get_unstaged_changes(changes)
        assert any(c.file_path == "README.md" for c in unstaged)

    def test_get_untracked_files(self, repo_with_initial_commit: Path):
        (repo_with_initial_commit / "untracked.txt").write_text("hi", encoding="utf-8")
        changes = get_repository_status(str(repo_with_initial_commit))
        untracked = get_untracked_files(changes)
        assert any(c.file_path == "untracked.txt" for c in untracked)
