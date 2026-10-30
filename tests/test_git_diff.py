"""Tests for git_engine/diff.py - staged, unstaged, and untracked diff extraction."""

import subprocess
from pathlib import Path
import pytest

from git_engine.diff import (
    extract_all_diffs,
    generate_untracked_diff,
    get_staged_diff,
    get_combined_tracked_diff,
    get_unstaged_diff,
    is_binary_file,
)
from config.settings import Settings


class TestIssBinaryFile:
    def test_text_file_not_binary(self, tmp_path: Path):
        f = tmp_path / "text.py"
        f.write_text("print('hello')\n", encoding="utf-8")
        assert is_binary_file(f) is False

    def test_binary_file_detected(self, tmp_path: Path):
        f = tmp_path / "binary.bin"
        f.write_bytes(b"\x00\x01\x02\x03some binary\x00data")
        assert is_binary_file(f) is True

    def test_missing_file_returns_false(self, tmp_path: Path):
        assert is_binary_file(tmp_path / "nonexistent.bin") is False


class TestGetUnstagedDiff:
    def test_no_changes_empty_diff(self, repo_with_initial_commit: Path):
        diff = get_unstaged_diff(str(repo_with_initial_commit))
        assert diff == ""

    def test_modified_file_produces_diff(self, repo_with_initial_commit: Path):
        readme = repo_with_initial_commit / "README.md"
        readme.write_text("# Modified\nNew content here\n", encoding="utf-8")
        diff = get_unstaged_diff(str(repo_with_initial_commit))
        assert "README.md" in diff
        assert "+" in diff

    def test_deleted_file_shows_in_diff(self, repo_with_initial_commit: Path):
        (repo_with_initial_commit / "README.md").unlink()
        diff = get_unstaged_diff(str(repo_with_initial_commit))
        assert "README.md" in diff
        assert "-" in diff


class TestGetStagedDiff:
    def test_no_staged_empty_diff(self, repo_with_initial_commit: Path):
        diff = get_staged_diff(str(repo_with_initial_commit))
        assert diff == ""

    def test_staged_new_file_shows_diff(self, repo_with_initial_commit: Path):
        new_file = repo_with_initial_commit / "new.py"
        new_file.write_text("x = 1\ny = 2\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "new.py"],
            cwd=str(repo_with_initial_commit),
            check=True,
            capture_output=True,
        )
        diff = get_staged_diff(str(repo_with_initial_commit))
        assert "new.py" in diff
        assert "+x = 1" in diff or "+x = 1\n" in diff

    def test_staged_different_from_unstaged(self, repo_with_initial_commit: Path):
        new_file = repo_with_initial_commit / "staged.py"
        new_file.write_text("x = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "staged.py"],
            cwd=str(repo_with_initial_commit),
            check=True,
            capture_output=True,
        )
        # Modify after staging so unstaged shows second change
        new_file.write_text("x = 1\ny = 2\n", encoding="utf-8")

        staged = get_staged_diff(str(repo_with_initial_commit))
        unstaged = get_unstaged_diff(str(repo_with_initial_commit))

        assert "staged.py" in staged
        assert "+y = 2" in unstaged or "y = 2" in unstaged


class TestGetCombinedTrackedDiff:
    def test_empty_diff_clean_repo(self, repo_with_initial_commit: Path):
        diff = get_combined_tracked_diff(str(repo_with_initial_commit))
        assert diff == ""

    def test_modified_shows_in_combined(self, repo_with_initial_commit: Path):
        (repo_with_initial_commit / "README.md").write_text("# Changed\n", encoding="utf-8")
        diff = get_combined_tracked_diff(str(repo_with_initial_commit))
        assert "README.md" in diff

    def test_falls_back_to_staged_for_initial_repo(self, temp_git_repo: Path):
        # No commits – should fall back to staged diff
        new_file = temp_git_repo / "first.py"
        new_file.write_text("a = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "first.py"],
            cwd=str(temp_git_repo),
            check=True,
            capture_output=True,
        )
        diff = get_combined_tracked_diff(str(temp_git_repo))
        assert "first.py" in diff


class TestGenerateUntrackedDiff:
    def test_generates_diff_for_text_file(self, repo_with_initial_commit: Path):
        text_file = repo_with_initial_commit / "new.txt"
        text_file.write_text("line1\nline2\n", encoding="utf-8")
        diff, truncated = generate_untracked_diff(
            ["new.txt"], repo_with_initial_commit, max_size=100000
        )
        assert "new.txt" in diff
        assert "+line1" in diff
        assert truncated is False

    def test_generates_binary_marker(self, repo_with_initial_commit: Path):
        binary = repo_with_initial_commit / "data.bin"
        binary.write_bytes(b"\x00\x01\x02binary_content")
        diff, _ = generate_untracked_diff(
            ["data.bin"], repo_with_initial_commit, max_size=100000
        )
        assert "Binary files" in diff
        assert "data.bin" in diff

    def test_truncation_at_size_limit(self, repo_with_initial_commit: Path):
        large_file = repo_with_initial_commit / "large.txt"
        large_file.write_text("x" * 1000 + "\n", encoding="utf-8")
        diff, truncated = generate_untracked_diff(
            ["large.txt"], repo_with_initial_commit, max_size=100, current_size=90
        )
        assert truncated is True

    def test_skips_nonexistent_files(self, repo_with_initial_commit: Path):
        diff, truncated = generate_untracked_diff(
            ["ghost.txt"], repo_with_initial_commit, max_size=100000
        )
        assert diff == ""
        assert truncated is False


class TestExtractAllDiffs:
    def test_clean_repo_all_empty(self, repo_with_initial_commit: Path):
        settings = Settings()
        diffs = extract_all_diffs(str(repo_with_initial_commit), settings=settings)
        assert diffs.staged_diff == ""
        assert diffs.unstaged_diff == ""
        assert diffs.is_truncated is False

    def test_captures_untracked(self, repo_with_initial_commit: Path):
        (repo_with_initial_commit / "new.txt").write_text("hello\n", encoding="utf-8")
        settings = Settings()
        diffs = extract_all_diffs(str(repo_with_initial_commit), settings=settings)
        assert "new.txt" in diffs.untracked_diff

    def test_multiple_file_types(self, repo_with_initial_commit: Path):
        (repo_with_initial_commit / "README.md").write_text("# Updated\n", encoding="utf-8")
        staged_f = repo_with_initial_commit / "staged.py"
        staged_f.write_text("x = 1\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "staged.py"],
            cwd=str(repo_with_initial_commit),
            check=True,
            capture_output=True,
        )
        untracked_f = repo_with_initial_commit / "new_untracked.txt"
        untracked_f.write_text("hello\n", encoding="utf-8")

        settings = Settings()
        diffs = extract_all_diffs(str(repo_with_initial_commit), settings=settings)
        assert "README.md" in diffs.unstaged_diff
        assert "staged.py" in diffs.staged_diff
        assert "new_untracked.txt" in diffs.untracked_diff
