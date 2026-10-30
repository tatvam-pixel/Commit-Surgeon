"""Tests for second-pass security and correctness fixes (Issues 1, 2, 3, 5B)."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_engine.context import prepare_change_context
from ai_engine.exceptions import ContextExceededLimitError
from config.settings import Settings
from git_engine.diff import (
    _run_git_diff_bounded,
    extract_all_diffs,
    generate_untracked_diff,
    is_binary_file,
)
from git_engine.models import DiffHunk, FileChange, RepositoryChanges, RepositoryInfo
from git_engine.parser import (
    _clean_git_header_path,
    _extract_file_paths_from_diff_git,
    _git_unquote,
    parse_unified_diff,
)


class TestSymlinkTargetNeverRead:
    """Issue 1 & 5B: Fully prevent untracked symlink target reads."""

    def test_internal_symlink_never_reads_target_os(self, tmp_path):
        """Internal symlink to a regular file must never have its target content in the diff."""
        repo = tmp_path / "repo"
        repo.mkdir()
        target = repo / "secret_internal.txt"
        target.write_text("SUPER_SECRET_INTERNAL_DATA\n", encoding="utf-8")

        link = repo / "link_internal.txt"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("OS does not permit symlink creation (requires Windows Developer Mode or admin)")

        diff, truncated = generate_untracked_diff(["link_internal.txt"], repo)
        assert "symbolic link ->" in diff
        assert "SUPER_SECRET_INTERNAL_DATA" not in diff
        assert "120000" in diff
        assert not truncated

    def test_external_symlink_never_reads_target_os(self, tmp_path):
        """External symlink to a file outside repo must never have its target content in the diff."""
        repo = tmp_path / "repo"
        repo.mkdir()
        secret = tmp_path / "outside_secret.txt"
        secret.write_text("FAKE_SECRET_OUTSIDE_REPO\n", encoding="utf-8")

        link = repo / "link_external.txt"
        try:
            link.symlink_to(secret)
        except OSError:
            pytest.skip("OS does not permit symlink creation (requires Windows Developer Mode or admin)")

        diff, truncated = generate_untracked_diff(["link_external.txt"], repo)
        assert "symbolic link ->" in diff
        assert "FAKE_SECRET_OUTSIDE_REPO" not in diff
        assert "120000" in diff
        assert not truncated

    def test_broken_symlink_consistently_handled_os(self, tmp_path):
        """Broken symlink must be represented safely by its link text without error."""
        repo = tmp_path / "repo"
        repo.mkdir()
        link = repo / "broken_link.txt"
        try:
            link.symlink_to(tmp_path / "nonexistent_target.txt")
        except OSError:
            pytest.skip("OS does not permit symlink creation (requires Windows Developer Mode or admin)")

        diff, truncated = generate_untracked_diff(["broken_link.txt"], repo)
        assert "symbolic link ->" in diff
        assert "nonexistent_target.txt" in diff
        assert "120000" in diff
        assert not truncated

    def test_symlink_to_directory_os(self, tmp_path):
        """Symlink to a directory must be represented as a link, not traversed."""
        repo = tmp_path / "repo"
        repo.mkdir()
        target_dir = tmp_path / "some_dir"
        target_dir.mkdir()
        (target_dir / "dir_file.txt").write_text("DIR_FILE_SECRET\n")

        link = repo / "dir_link"
        try:
            link.symlink_to(target_dir, target_is_directory=True)
        except OSError:
            pytest.skip("OS does not permit symlink creation (requires Windows Developer Mode or admin)")

        diff, truncated = generate_untracked_diff(["dir_link"], repo)
        assert "symbolic link ->" in diff
        assert "DIR_FILE_SECRET" not in diff
        assert "120000" in diff

    # Guaranteed mock-based tests that run and verify all scenarios on any platform
    def test_mock_internal_symlink_target_never_read(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        with patch.object(Path, "is_symlink", return_value=True), \
             patch("os.readlink", return_value="real_target.txt"):
            diff, truncated = generate_untracked_diff(["my_link.txt"], repo)
            assert "symbolic link -> real_target.txt" in diff
            assert "120000" in diff
            assert not truncated

    def test_mock_external_symlink_target_never_read(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        with patch.object(Path, "is_symlink", return_value=True), \
             patch("os.readlink", return_value="../../etc/passwd"):
            diff, truncated = generate_untracked_diff(["evil_link"], repo)
            assert "symbolic link -> ../../etc/passwd" in diff
            assert "120000" in diff
            assert not truncated

    def test_mock_broken_symlink_handled(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        with patch.object(Path, "is_symlink", return_value=True), \
             patch("os.readlink", return_value="dead_target.txt"):
            diff, truncated = generate_untracked_diff(["dangling.txt"], repo)
            assert "symbolic link -> dead_target.txt" in diff
            assert "120000" in diff

    def test_mock_symlink_to_directory_not_traversed(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        with patch.object(Path, "is_symlink", return_value=True), \
             patch("os.readlink", return_value="target_folder"):
            diff, truncated = generate_untracked_diff(["folder_link"], repo)
            assert "symbolic link -> target_folder" in diff
            assert "120000" in diff

    def test_normal_untracked_file_content_included(self, tmp_path):
        """Normal files have their content included in the diff."""
        repo = tmp_path / "repo"
        repo.mkdir()
        f = repo / "hello.py"
        f.write_text("print('hello world')\n", encoding="utf-8")

        diff, truncated = generate_untracked_diff(["hello.py"], repo)
        assert "print('hello world')" in diff
        assert "symbolic link" not in diff

    def test_is_binary_file_never_follows_symlink(self, tmp_path):
        fake_file = tmp_path / "symlink_file"
        with patch.object(Path, "is_symlink", return_value=True):
            assert is_binary_file(fake_file) is False


class TestMemoryBoundedDiffExtraction:
    """Issue 2: Bounded subprocess reading and size limit enforcement."""

    def test_diff_below_limit(self, repo_with_initial_commit):
        readme = repo_with_initial_commit / "README.md"
        readme.write_text("updated content below limit\n", encoding="utf-8")
        diff_text, is_trunc = _run_git_diff_bounded(
            ["diff", "--no-ext-diff"],
            cwd=str(repo_with_initial_commit),
            max_chars=10000,
        )
        assert is_trunc is False
        assert "updated content below limit" in diff_text

    def test_diff_above_limit_truncates(self, repo_with_initial_commit):
        readme = repo_with_initial_commit / "README.md"
        readme.write_text("a" * 500 + "\n", encoding="utf-8")
        diff_text, is_trunc = _run_git_diff_bounded(
            ["diff", "--no-ext-diff"],
            cwd=str(repo_with_initial_commit),
            max_chars=100,
        )
        assert is_trunc is True
        assert len(diff_text) <= 100

    def test_oversized_unstaged_truncates_and_skips_further_reads(self, repo_with_initial_commit):
        f = repo_with_initial_commit / "file.txt"
        f.write_text("x" * 300 + "\n", encoding="utf-8")

        settings = Settings(max_diff_size=50)
        diffs = extract_all_diffs(str(repo_with_initial_commit), settings=settings)
        assert diffs.is_truncated is True
        assert diffs.staged_diff == ""
        assert diffs.untracked_diff == ""
        assert len(diffs.unstaged_diff) <= 50

    def test_oversized_staged_diff_truncates(self, repo_with_initial_commit):
        f = repo_with_initial_commit / "file.txt"
        f.write_text("s" * 300 + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(repo_with_initial_commit), check=True)

        settings = Settings(max_diff_size=60)
        diffs = extract_all_diffs(str(repo_with_initial_commit), settings=settings)
        assert diffs.is_truncated is True
        assert len(diffs.staged_diff) <= 60
        assert diffs.untracked_diff == ""

    def test_combined_staged_and_unstaged_exceeding_limit(self, repo_with_initial_commit):
        f = repo_with_initial_commit / "file.txt"
        # Staged change of 40 chars
        f.write_text("staged " * 5 + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "file.txt"], cwd=str(repo_with_initial_commit), check=True)
        # Unstaged change of 40 chars
        f.write_text("staged " * 5 + "\nunstaged " * 5 + "\n", encoding="utf-8")

        settings = Settings(max_diff_size=80)
        diffs = extract_all_diffs(str(repo_with_initial_commit), settings=settings)
        assert diffs.is_truncated is True

    def test_large_untracked_file_bounded_reading(self, tmp_path):
        """Untracked file larger than limit does not buffer entirely in memory."""
        repo = tmp_path / "repo"
        repo.mkdir()
        big_file = repo / "huge.txt"
        big_file.write_text("line\n" * 1000, encoding="utf-8")

        diff, is_trunc = generate_untracked_diff(["huge.txt"], repo, max_size=100)
        assert is_trunc is True
        assert len(diff) <= 100

    def test_bounded_subprocess_terminates_process_early(self):
        """Subprocess must be terminated when output exceeds limit to save memory and CPU."""
        mock_proc = MagicMock()
        mock_stdout = MagicMock()
        # Simulate an infinite stream of 1000-byte chunks
        mock_stdout.read.return_value = b"x" * 1000
        mock_proc.stdout = mock_stdout
        mock_proc.returncode = 0

        with patch("subprocess.Popen", return_value=mock_proc):
            diff, is_trunc = _run_git_diff_bounded(
                ["diff"],
                cwd=".",
                max_chars=500,
            )
            assert is_trunc is True
            assert len(diff) == 500
            # Verify proc.terminate() was called to stop the process
            mock_proc.terminate.assert_called_once()

    def test_truncated_diff_blocks_ai_grouping(self):
        """Truncated diff extraction must raise ContextExceededLimitError and block LLM."""
        repo = RepositoryInfo(root_path="/fake/repo", current_branch="main")
        fc = FileChange(
            file_path="huge.py",
            hunks=[DiffHunk(hunk_id="h1", source_state="staged", added_lines=100)],
        )
        changes = RepositoryChanges(
            repository=repo,
            changes=[fc],
            total_files=1,
            has_truncated_content=True,
        )

        with pytest.raises(ContextExceededLimitError, match="truncated due to repository size limits"):
            prepare_change_context(changes, settings=Settings())


class TestUnambiguousGitDiffPathParsing:
    """Issue 3: Parsing paths without ambiguous string heuristics."""

    def test_path_with_spaces(self):
        diff = (
            "diff --git a/src/my file.py b/src/my file.py\n"
            "--- a/src/my file.py\n"
            "+++ b/src/my file.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+new line\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].file_path == "src/my file.py"

    def test_path_with_quotes(self):
        diff = (
            'diff --git "a/path/\\"quoted\\"/file.py" "b/path/\\"quoted\\"/file.py"\n'
            '--- "a/path/\\"quoted\\"/file.py"\n'
            '+++ "b/path/\\"quoted\\"/file.py"\n'
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+new line\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].file_path == 'path/"quoted"/file.py'

    def test_path_with_tabs(self):
        diff = (
            'diff --git "a/src/tab\\tfile.py" "b/src/tab\\tfile.py"\n'
            '--- "a/src/tab\\tfile.py"\n'
            '+++ "b/src/tab\\tfile.py"\n'
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+new line\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].file_path == "src/tab\tfile.py"

    def test_path_with_unicode(self):
        diff = (
            "diff --git a/données/résumé.py b/données/résumé.py\n"
            "--- a/données/résumé.py\n"
            "+++ b/données/résumé.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+nouvelle ligne\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].file_path == "données/résumé.py"

    def test_literal_b_slash_in_filename(self):
        """Paths containing literal ' b/' must not be broken by splitting."""
        diff = (
            "diff --git a/src/ b/utils.py b/src/ b/utils.py\n"
            "--- a/src/ b/utils.py\n"
            "+++ b/src/ b/utils.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+new line\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].file_path == "src/ b/utils.py"

    def test_rename_with_unusual_filenames(self):
        """Rename headers must unambiguously define old and new paths."""
        diff = (
            "diff --git a/old path with spaces.py b/new path with spaces.py\n"
            "similarity index 98%\n"
            "rename from old path with spaces.py\n"
            "rename to new path with spaces.py\n"
            "--- a/old path with spaces.py\n"
            "+++ b/new path with spaces.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+renamed addition\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].change_type == "renamed"
        assert changes[0].old_path == "old path with spaces.py"
        assert changes[0].new_path == "new path with spaces.py"
        assert changes[0].file_path == "new path with spaces.py"

    def test_deletion_path_resolution(self):
        """Deleted files where +++ is /dev/null must resolve to old_path."""
        diff = (
            "diff --git a/src/deleted file.py b/src/deleted file.py\n"
            "deleted file mode 100644\n"
            "--- a/src/deleted file.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "-line 1\n"
            "-line 2\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].change_type == "deleted"
        assert changes[0].file_path == "src/deleted file.py"

    def test_copy_path_resolution(self):
        """Copied files must extract copy from and copy to paths."""
        diff = (
            "diff --git a/src/orig.py b/src/copy.py\n"
            "copy from src/orig.py\n"
            "copy to src/copy.py\n"
            "--- a/src/orig.py\n"
            "+++ b/src/copy.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+copy edit\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 1
        assert changes[0].change_type == "copied"
        assert changes[0].old_path == "src/orig.py"
        assert changes[0].new_path == "src/copy.py"
        assert changes[0].file_path == "src/copy.py"

    def test_authoritative_known_paths_matching(self):
        """When known_paths are supplied, parser uses exact matching."""
        diff = (
            "diff --git a/src/utils.py b/src/utils.py\n"
            "--- a/src/utils.py\n"
            "+++ b/src/utils.py\n"
            "@@ -1,1 +1,2 @@\n"
            " a\n"
            "+b\n"
        )
        changes = parse_unified_diff(diff, known_paths=["src/utils.py", "other.py"])
        assert len(changes) == 1
        assert changes[0].file_path == "src/utils.py"

    def test_multiple_files_with_similar_names(self):
        """Similar names like src/a_b.py and src_a/b.py must not be confused."""
        diff = (
            "diff --git a/src/a_b.py b/src/a_b.py\n"
            "--- a/src/a_b.py\n"
            "+++ b/src/a_b.py\n"
            "@@ -1,1 +1,2 @@\n"
            " 1\n"
            "+2\n"
            "diff --git a/src_a/b.py b/src_a/b.py\n"
            "--- a/src_a/b.py\n"
            "+++ b/src_a/b.py\n"
            "@@ -1,1 +1,2 @@\n"
            " 3\n"
            "+4\n"
        )
        changes = parse_unified_diff(diff)
        assert len(changes) == 2
        assert changes[0].file_path == "src/a_b.py"
        assert changes[1].file_path == "src_a/b.py"
        assert changes[0].hunks[0].hunk_id != changes[1].hunks[0].hunk_id
