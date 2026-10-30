"""Regression tests for staged vs unstaged hunk separation and statistics."""

import re
import subprocess
from pathlib import Path
import pytest

from git_engine.analyzer import analyze_repository
from git_engine.models import DiffHunk, FileChange, RepositoryChanges, RepositoryInfo
from git_engine.parser import parse_unified_diff
from main import run_analyze


def _strip_ansi(text: str) -> str:
    """Strip ANSI color codes so assertions work regardless of terminal styling."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


class TestDiffHunkSourceState:
    """Test DiffHunk source state tracking and properties."""

    def test_default_source_state_unstaged(self):
        hunk = DiffHunk(hunk_id="h1")
        assert hunk.source_state == "unstaged"
        assert hunk.is_unstaged is True
        assert hunk.is_staged is False
        assert hunk.is_untracked is False
        assert hunk.source == "unstaged"

    def test_staged_source_state(self):
        hunk = DiffHunk(hunk_id="h2", source_state="staged")
        assert hunk.source_state == "staged"
        assert hunk.is_staged is True
        assert hunk.is_unstaged is False
        assert hunk.is_untracked is False

    def test_untracked_source_state(self):
        hunk = DiffHunk(hunk_id="h3", source_state="untracked")
        assert hunk.source_state == "untracked"
        assert hunk.is_untracked is True
        assert hunk.is_staged is False
        assert hunk.is_unstaged is False


class TestParseUnifiedDiffSourceAttribution:
    """Test parse_unified_diff preserves provided source_state."""

    def test_parse_staged_diff(self):
        diff_text = (
            "diff --git a/test.py b/test.py\n"
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,2 +1,3 @@\n"
            " line1\n"
            "+staged_line\n"
            " line2\n"
        )
        changes = parse_unified_diff(diff_text, source_state="staged")
        assert len(changes) == 1
        fc = changes[0]
        assert fc.is_staged is True
        assert fc.staged_added_lines == 1
        assert fc.unstaged_added_lines == 0
        assert len(fc.hunks) == 1
        assert fc.hunks[0].source_state == "staged"
        assert fc.hunks[0].is_staged is True

    def test_parse_unstaged_diff_default(self):
        diff_text = (
            "diff --git a/test.py b/test.py\n"
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-old_line\n"
            "+new_line\n"
        )
        changes = parse_unified_diff(diff_text)
        assert len(changes) == 1
        fc = changes[0]
        assert fc.is_staged is False
        assert fc.is_unstaged is True
        assert fc.staged_deleted_lines == 0
        assert fc.unstaged_deleted_lines == 1
        assert fc.unstaged_added_lines == 1
        assert len(fc.hunks) == 1
        assert fc.hunks[0].source_state == "unstaged"


class TestModelsHunkSeparationStats:
    """Test FileChange and RepositoryChanges aggregate and separated statistics."""

    def test_file_change_properties_and_hunk_separation(self):
        hunk_staged = DiffHunk(
            hunk_id="h_s",
            source_state="staged",
            added_lines=2,
            deleted_lines=1,
        )
        hunk_unstaged = DiffHunk(
            hunk_id="h_u",
            source_state="unstaged",
            added_lines=3,
            deleted_lines=0,
        )
        fc = FileChange(
            file_path="sample.py",
            hunks=[hunk_staged, hunk_unstaged],
        )

        assert fc.staged_added_lines == 2
        assert fc.staged_deleted_lines == 1
        assert fc.unstaged_added_lines == 3
        assert fc.unstaged_deleted_lines == 0
        assert len(fc.staged_hunks) == 1
        assert len(fc.unstaged_hunks) == 1

    def test_repository_changes_separate_statistics(self):
        repo_info = RepositoryInfo(root_path="/fake/path")
        hunk_s = DiffHunk(hunk_id="h1", source_state="staged", added_lines=2, deleted_lines=2)
        hunk_u = DiffHunk(hunk_id="h2", source_state="unstaged", added_lines=3, deleted_lines=0)
        fc = FileChange(file_path="auth.py", hunks=[hunk_s, hunk_u], added_lines=5, deleted_lines=2)

        repo_changes = RepositoryChanges(
            repository=repo_info,
            changes=[fc],
            total_files=1,
            total_added_lines=5,
            total_deleted_lines=2,
            total_hunks=2,
            staged_added_lines=2,
            staged_deleted_lines=2,
            unstaged_added_lines=3,
            unstaged_deleted_lines=0,
            staged_hunks=1,
            unstaged_hunks=1,
        )

        assert repo_changes.staged_added_lines == 2
        assert repo_changes.staged_deleted_lines == 2
        assert repo_changes.unstaged_added_lines == 3
        assert repo_changes.unstaged_deleted_lines == 0
        assert repo_changes.staged_hunks == 1
        assert repo_changes.unstaged_hunks == 1
        assert repo_changes.total_added_lines == 5
        assert repo_changes.total_deleted_lines == 2
        assert repo_changes.total_hunks == 2
        assert len(repo_changes.get_staged_hunks()) == 1
        assert len(repo_changes.get_unstaged_hunks()) == 1


class TestAnalyzerStagedUnstagedSeparation:
    """Test full repository analysis with both staged and unstaged changes."""

    def test_mixed_staged_and_unstaged_in_same_file(self, repo_with_initial_commit: Path):
        f = repo_with_initial_commit / "file.txt"
        f.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(repo_with_initial_commit), check=True)
        subprocess.run(["git", "commit", "-m", "add file.txt"], cwd=str(repo_with_initial_commit), check=True)

        # Stage a modification (1 deleted, 1 added)
        f.write_text("line 1 (staged)\nline 2\nline 3\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(repo_with_initial_commit), check=True)

        # Make an unstaged modification (1 added)
        f.write_text("line 1 (staged)\nline 2\nline 3\nline 4 (unstaged)\n", encoding="utf-8")

        changes = analyze_repository(str(repo_with_initial_commit))

        assert changes.total_files == 1
        fc = changes.changes[0]
        assert fc.is_staged is True
        assert fc.is_unstaged is True

        assert changes.staged_added_lines == 1
        assert changes.staged_deleted_lines == 1
        assert changes.staged_hunks == 1

        assert changes.unstaged_added_lines == 1
        assert changes.unstaged_deleted_lines == 0
        assert changes.unstaged_hunks == 1

        assert changes.total_added_lines == 2
        assert changes.total_deleted_lines == 1
        assert changes.total_hunks == 2


class TestAuditRepositoryOutput:
    """Test specific expected statistics on audit repository state (staged: +2/-2, unstaged: +3/-0)."""

    @pytest.fixture
    def audit_repo(self, repo_with_initial_commit: Path) -> Path:
        """Create a reproducible repository matching the exact audit state."""
        auth_file = repo_with_initial_commit / "auth.py"
        auth_file.write_text(
            "def login():\n    return False\n\ndef logout():\n    return False\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "auth.py"], cwd=str(repo_with_initial_commit), check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial auth"],
            cwd=str(repo_with_initial_commit),
            check=True,
        )

        # Stage change (+2, -2)
        auth_file.write_text(
            "def login():\n    return True\n\ndef logout():\n    return True\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "auth.py"], cwd=str(repo_with_initial_commit), check=True)

        # Unstaged change (+3, -0)
        auth_file.write_text(
            "def login():\n    return True\n\ndef logout():\n    return True\n\ndef validate_user():\n    return True\n",
            encoding="utf-8",
        )
        return repo_with_initial_commit

    def test_audit_repo_statistics(self, audit_repo: Path):
        changes = analyze_repository(str(audit_repo))
        assert changes.staged_added_lines == 2
        assert changes.staged_deleted_lines == 2
        assert changes.unstaged_added_lines == 3
        assert changes.unstaged_deleted_lines == 0
        assert changes.total_added_lines == 5
        assert changes.total_deleted_lines == 2
        assert changes.total_hunks == 2

    def test_audit_repo_cli_output(self, audit_repo: Path, capsys):
        exit_code = run_analyze(str(audit_repo))
        assert exit_code == 0
        captured = _strip_ansi(capsys.readouterr().out)

        assert "Staged:\n- Added lines: 2\n- Deleted lines: 2" in captured
        assert "Unstaged:\n- Added lines: 3\n- Deleted lines: 0" in captured
        assert "Total:\n- Added lines: 5\n- Deleted lines: 2\n- Hunks: 2" in captured
