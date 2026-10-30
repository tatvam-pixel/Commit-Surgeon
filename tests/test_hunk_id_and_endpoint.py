"""Tests for hunk ID collision prevention and remote endpoint warning (P2 #4, P2 #10)."""

import hashlib
import pytest

from git_engine.parser import parse_unified_diff
from utils.environment import is_loopback_url, EnvironmentReport, ComponentStatus, run_environment_check
from config.settings import Settings


class TestHunkIdCollisions:
    """Fix #4: Hunk IDs should not collide for different paths."""

    def test_collision_paths_produce_different_ids(self):
        """src/a_b.py and src_a/b.py should have different hunk IDs."""
        diff1 = (
            "diff --git a/src/a_b.py b/src/a_b.py\n"
            "--- a/src/a_b.py\n"
            "+++ b/src/a_b.py\n"
            "@@ -1,1 +1,2 @@\n"
            " existing\n"
            "+new1\n"
        )
        diff2 = (
            "diff --git a/src_a/b.py b/src_a/b.py\n"
            "--- a/src_a/b.py\n"
            "+++ b/src_a/b.py\n"
            "@@ -1,1 +1,2 @@\n"
            " existing\n"
            "+new2\n"
        )
        
        changes1 = parse_unified_diff(diff1, source_state="staged")
        changes2 = parse_unified_diff(diff2, source_state="staged")
        
        id1 = changes1[0].hunks[0].hunk_id
        id2 = changes2[0].hunks[0].hunk_id
        assert id1 != id2, f"Hunk IDs should differ but both are: {id1}"

    def test_hunk_id_deterministic(self):
        """Same input should always produce same hunk ID."""
        diff = (
            "diff --git a/test.py b/test.py\n"
            "--- a/test.py\n"
            "+++ b/test.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+added\n"
        )
        c1 = parse_unified_diff(diff, source_state="unstaged")
        c2 = parse_unified_diff(diff, source_state="unstaged")
        assert c1[0].hunks[0].hunk_id == c2[0].hunks[0].hunk_id

    def test_hunk_id_contains_hash(self):
        """Hunk ID should contain a hash component."""
        diff = (
            "diff --git a/src/utils.py b/src/utils.py\n"
            "--- a/src/utils.py\n"
            "+++ b/src/utils.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+added\n"
        )
        changes = parse_unified_diff(diff, source_state="staged")
        hunk_id = changes[0].hunks[0].hunk_id
        expected_hash = hashlib.sha256("src/utils.py".encode("utf-8")).hexdigest()[:12]
        assert expected_hash in hunk_id

    def test_same_file_staged_unstaged_different_ids(self):
        """Same file parsed as staged vs unstaged should produce different hunk IDs."""
        diff = (
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+added\n"
        )
        staged = parse_unified_diff(diff, source_state="staged")
        unstaged = parse_unified_diff(diff, source_state="unstaged")
        assert staged[0].hunks[0].hunk_id != unstaged[0].hunks[0].hunk_id

    def test_multi_hunk_unique_ids(self):
        """Multiple hunks in the same file should have unique IDs."""
        diff = (
            "diff --git a/file.py b/file.py\n"
            "--- a/file.py\n"
            "+++ b/file.py\n"
            "@@ -1,3 +1,4 @@\n"
            " line1\n"
            "+added1\n"
            " line2\n"
            " line3\n"
            "@@ -10,3 +11,4 @@\n"
            " line10\n"
            "+added2\n"
            " line11\n"
            " line12\n"
        )
        changes = parse_unified_diff(diff, source_state="staged")
        ids = [h.hunk_id for h in changes[0].hunks]
        assert len(ids) == len(set(ids)), "Hunk IDs within same file must be unique"

    def test_unicode_path_no_error(self):
        """Unicode file paths should not cause errors."""
        diff = (
            "diff --git a/données/résumé.py b/données/résumé.py\n"
            "--- a/données/résumé.py\n"
            "+++ b/données/résumé.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+ajouté\n"
        )
        changes = parse_unified_diff(diff, source_state="staged")
        assert len(changes) == 1
        assert len(changes[0].hunks) == 1

    def test_path_with_spaces_no_error(self):
        """File paths with spaces should produce valid hunk IDs."""
        diff = (
            "diff --git a/my project/main file.py b/my project/main file.py\n"
            "--- a/my project/main file.py\n"
            "+++ b/my project/main file.py\n"
            "@@ -1,1 +1,2 @@\n"
            " line\n"
            "+added\n"
        )
        changes = parse_unified_diff(diff, source_state="staged")
        assert len(changes) == 1
        hunk_id = changes[0].hunks[0].hunk_id
        assert "hunk_" in hunk_id


class TestRemoteEndpointWarning:
    """Fix #10: Warn when OLLAMA_API_URL is non-loopback."""

    def test_localhost_is_loopback(self):
        assert is_loopback_url("http://localhost:11434") is True

    def test_127_is_loopback(self):
        assert is_loopback_url("http://127.0.0.1:11434") is True

    def test_ipv6_loopback(self):
        assert is_loopback_url("http://[::1]:11434") is True

    def test_remote_ip_not_loopback(self):
        assert is_loopback_url("http://192.168.1.100:11434") is False

    def test_remote_hostname_not_loopback(self):
        assert is_loopback_url("http://ollama.example.com:11434") is False

    def test_empty_url(self):
        assert is_loopback_url("") is False

    def test_invalid_url(self):
        assert is_loopback_url("not-a-url") is False

    def test_environment_report_has_warning_field(self):
        """EnvironmentReport should have an endpoint_warning field."""
        dummy = ComponentStatus(name="Test", label="OK", is_ok=True)
        report = EnvironmentReport(
            python=dummy,
            git=dummy,
            ollama=dummy,
            model=dummy,
            endpoint_warning="test warning",
        )
        assert report.endpoint_warning == "test warning"

    def test_no_warning_for_localhost(self):
        """Default localhost should not trigger warning."""
        dummy = ComponentStatus(name="Test", label="OK", is_ok=True)
        report = EnvironmentReport(
            python=dummy,
            git=dummy,
            ollama=dummy,
            model=dummy,
        )
        assert report.endpoint_warning is None
