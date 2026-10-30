"""Tests for git_engine/parser.py - unified diff parsing and hunk extraction."""

import pytest

from git_engine.exceptions import DiffParsingError
from git_engine.parser import parse_hunk_header, parse_unified_diff


class TestParseHunkHeader:
    def test_standard_header(self):
        old_s, old_c, new_s, new_c = parse_hunk_header("@@ -10,3 +10,5 @@")
        assert old_s == 10
        assert old_c == 3
        assert new_s == 10
        assert new_c == 5

    def test_header_with_context_label(self):
        old_s, old_c, new_s, new_c = parse_hunk_header("@@ -1,4 +1,6 @@ def my_function():")
        assert old_s == 1
        assert old_c == 4
        assert new_s == 1
        assert new_c == 6

    def test_header_zero_old_count(self):
        old_s, old_c, new_s, new_c = parse_hunk_header("@@ -0,0 +1,5 @@")
        assert old_s == 0
        assert old_c == 0
        assert new_s == 1
        assert new_c == 5

    def test_header_without_counts(self):
        # @@ -1 +1 @@ means count defaults to 1
        old_s, old_c, new_s, new_c = parse_hunk_header("@@ -1 +1 @@")
        assert old_s == 1
        assert old_c == 1
        assert new_s == 1
        assert new_c == 1

    def test_header_without_old_count(self):
        old_s, old_c, new_s, new_c = parse_hunk_header("@@ -5 +5,3 @@")
        assert old_s == 5
        assert old_c == 1
        assert new_s == 5
        assert new_c == 3

    def test_invalid_header_raises(self):
        with pytest.raises(DiffParsingError):
            parse_hunk_header("not a hunk header at all")

    def test_empty_string_raises(self):
        with pytest.raises(DiffParsingError):
            parse_hunk_header("")


class TestParseUnifiedDiff:
    def test_empty_diff(self):
        result = parse_unified_diff("")
        assert result == []

    def test_whitespace_only_diff(self):
        result = parse_unified_diff("   \n\n  ")
        assert result == []

    def test_single_hunk_modification(self):
        diff = (
            "diff --git a/file.py b/file.py\n"
            "index abc1234..def5678 100644\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -10,3 +10,5 @@\n"
            " context line\n"
            "-removed line\n"
            "+added line 1\n"
            "+added line 2\n"
            " context line 2\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        fc = result[0]
        assert fc.file_path == "file.py"
        assert len(fc.hunks) == 1
        hunk = fc.hunks[0]
        assert hunk.old_start == 10
        assert hunk.old_count == 3
        assert hunk.new_start == 10
        assert hunk.new_count == 5
        assert hunk.added_lines == 2
        assert hunk.deleted_lines == 1
        assert fc.added_lines == 2
        assert fc.deleted_lines == 1

    def test_multiple_hunks_in_one_file(self):
        diff = (
            "diff --git a/app.py b/app.py\n"
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+new line\n"
            " line2\n"
            " line3\n"
            "@@ -20,3 +21,2 @@\n"
            " line20\n"
            "-removed\n"
            " line22\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        fc = result[0]
        assert len(fc.hunks) == 2
        assert fc.hunks[0].added_lines == 1
        assert fc.hunks[0].deleted_lines == 0
        assert fc.hunks[1].added_lines == 0
        assert fc.hunks[1].deleted_lines == 1
        assert fc.added_lines == 1
        assert fc.deleted_lines == 1

    def test_multiple_files_in_diff(self):
        diff = (
            "diff --git a/file1.py b/file1.py\n"
            "--- a/file1.py\n"
            "+++ b/file1.py\n"
            "@@ -1,1 +1,2 @@\n"
            " x = 1\n"
            "+y = 2\n"
            "diff --git a/file2.py b/file2.py\n"
            "--- a/file2.py\n"
            "+++ b/file2.py\n"
            "@@ -5,2 +5,1 @@\n"
            " alpha\n"
            "-beta\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 2
        paths = {fc.file_path for fc in result}
        assert "file1.py" in paths
        assert "file2.py" in paths

    def test_added_file(self):
        diff = (
            "diff --git a/new.py b/new.py\n"
            "new file mode 100644\n"
            "index 0000000..aaaaaaa\n"
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+line1\n"
            "+line2\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        assert result[0].change_type == "added"
        assert result[0].added_lines == 2
        assert result[0].deleted_lines == 0

    def test_deleted_file(self):
        diff = (
            "diff --git a/old.py b/old.py\n"
            "deleted file mode 100644\n"
            "index aaaaaaa..0000000\n"
            "--- a/old.py\n"
            "+++ /dev/null\n"
            "@@ -1,2 +0,0 @@\n"
            "-line1\n"
            "-line2\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        assert result[0].change_type == "deleted"
        assert result[0].deleted_lines == 2
        assert result[0].added_lines == 0

    def test_renamed_file(self):
        diff = (
            "diff --git a/old.py b/new.py\n"
            "similarity index 100%\n"
            "rename from old.py\n"
            "rename to new.py\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        assert result[0].change_type == "renamed"
        assert result[0].old_path == "old.py"
        assert result[0].new_path == "new.py"

    def test_binary_file_marker(self):
        diff = (
            "diff --git a/image.png b/image.png\n"
            "index abc..def 100644\n"
            "Binary files a/image.png and b/image.png differ\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        assert result[0].is_binary is True
        assert len(result[0].hunks) == 0

    def test_malformed_diff_no_crash(self):
        # Should not raise, return best-effort result
        diff = "this is not a unified diff at all\n"
        result = parse_unified_diff(diff)
        assert isinstance(result, list)

    def test_hunk_content_preserved(self):
        diff = (
            "diff --git a/f.py b/f.py\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,2 +1,3 @@\n"
            " same\n"
            "+new\n"
            " end\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
        hunk = result[0].hunks[0]
        assert " same" in hunk.content
        assert "+new" in hunk.content
        assert "@@" in hunk.header

    def test_filename_with_spaces(self):
        diff = (
            "diff --git a/my file.py b/my file.py\n"
            "--- a/my file.py\n"
            "+++ b/my file.py\n"
            "@@ -1,1 +1,2 @@\n"
            " x = 1\n"
            "+y = 2\n"
        )
        result = parse_unified_diff(diff)
        assert len(result) == 1
