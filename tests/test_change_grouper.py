"""Unit tests for the ChangeGrouper high-level grouping engine."""

import json
from unittest.mock import MagicMock
import pytest

from ai_engine.grouper import ChangeGrouper, group_repository_changes
from ai_engine.models import GroupingResult, ProposedCommitGroup
from ai_engine.ollama_client import OllamaClient
from git_engine.models import DiffHunk, FileChange, RepositoryChanges, RepositoryInfo


@pytest.fixture
def complex_repo_changes():
    """Create a multi-file, multi-hunk repository change set matching Section 7 example."""
    repo_info = RepositoryInfo(root_path="/app", current_branch="feature/auth-and-ui")

    # auth.py has 2 hunks: hunk 1 (fix login), hunk 2 (update logging)
    hunk_auth_1 = DiffHunk(
        hunk_id="hunk_1_auth",
        source_state="staged",
        header="@@ -1,5 +1,5 @@",
        content="+return True\n-return False\n",
        added_lines=1,
        deleted_lines=1,
    )
    hunk_auth_2 = DiffHunk(
        hunk_id="hunk_2_auth_logging",
        source_state="unstaged",
        header="@@ -20,3 +20,4 @@",
        content="+logger.info('User authenticated')\n",
        added_lines=1,
        deleted_lines=0,
    )
    fc_auth = FileChange(
        file_path="auth.py",
        hunks=[hunk_auth_1, hunk_auth_2],
        is_staged=True,
        is_unstaged=True,
    )

    # middleware.py has 1 hunk
    hunk_middleware = DiffHunk(
        hunk_id="hunk_1_middleware",
        source_state="staged",
        header="@@ -10,4 +10,6 @@",
        content="+check_token(req)\n",
        added_lines=1,
        deleted_lines=0,
    )
    fc_middleware = FileChange(
        file_path="middleware.py",
        hunks=[hunk_middleware],
        is_staged=True,
    )

    # home.py has 1 hunk
    hunk_home = DiffHunk(
        hunk_id="hunk_1_home",
        source_state="unstaged",
        header="@@ -5,3 +5,6 @@",
        content="+render_hero_banner()\n",
        added_lines=1,
        deleted_lines=0,
    )
    fc_home = FileChange(
        file_path="home.py",
        hunks=[hunk_home],
        is_unstaged=True,
    )

    # README.md has 1 hunk
    hunk_readme = DiffHunk(
        hunk_id="hunk_1_readme",
        source_state="unstaged",
        header="@@ -1,2 +1,3 @@",
        content="+# Installation\n",
        added_lines=1,
        deleted_lines=0,
    )
    fc_readme = FileChange(
        file_path="README.md",
        hunks=[hunk_readme],
        is_unstaged=True,
    )

    return RepositoryChanges(
        repository=repo_info,
        changes=[fc_auth, fc_middleware, fc_home, fc_readme],
        total_files=4,
    )


class TestChangeGrouper:
    """Test ChangeGrouper logic and semantic clustering."""

    def test_semantic_grouping_and_different_hunk_separation(self, complex_repo_changes):
        """Verify cross-file grouping and same-file different-hunk grouping."""
        expected_llm_json = json.dumps({
            "analysis_summary": "Detected authentication fix, logging update, UI changes, and documentation.",
            "change_analyses": [
                {
                    "change_id": "hunk_1_auth",
                    "file_path": "auth.py",
                    "source_state": "staged",
                    "summary": "Fix login validation",
                    "purpose": "Fix login logic",
                    "affected_functionality": "Auth",
                    "confidence": 0.95,
                    "uncertainty_reason": None,
                },
                {
                    "change_id": "hunk_2_auth_logging",
                    "file_path": "auth.py",
                    "source_state": "unstaged",
                    "summary": "Add debug logging",
                    "purpose": "Logging",
                    "affected_functionality": "Auth logging",
                    "confidence": 0.92,
                    "uncertainty_reason": None,
                },
                {
                    "change_id": "hunk_1_middleware",
                    "file_path": "middleware.py",
                    "source_state": "staged",
                    "summary": "Check token",
                    "purpose": "Token check",
                    "affected_functionality": "Auth middleware",
                    "confidence": 0.94,
                    "uncertainty_reason": None,
                },
                {
                    "change_id": "hunk_1_home",
                    "file_path": "home.py",
                    "source_state": "unstaged",
                    "summary": "Render hero banner",
                    "purpose": "UI update",
                    "affected_functionality": "Homepage UI",
                    "confidence": 0.96,
                    "uncertainty_reason": None,
                },
                {
                    "change_id": "hunk_1_readme",
                    "file_path": "README.md",
                    "source_state": "unstaged",
                    "summary": "Update install docs",
                    "purpose": "Documentation",
                    "affected_functionality": "Docs",
                    "confidence": 0.98,
                    "uncertainty_reason": None,
                },
            ],
            "proposed_groups": [
                {
                    "group_id": "group_1",
                    "suggested_title": "fix(auth): update login validation and middleware",
                    "summary": "Fixes core authentication logic and checks token in middleware.",
                    "change_ids": ["hunk_1_auth", "hunk_1_middleware"],
                    "reasoning": "Both hunks implement the core authentication validation flow.",
                    "confidence": 0.94,
                    "uncertainty_flags": [],
                },
                {
                    "group_id": "group_2",
                    "suggested_title": "chore(logging): add authentication debug logger",
                    "summary": "Adds logging to auth workflow.",
                    "change_ids": ["hunk_2_auth_logging"],
                    "reasoning": "Separate logging modification from the functional bug fix in auth.py.",
                    "confidence": 0.90,
                    "uncertainty_flags": [],
                },
                {
                    "group_id": "group_3",
                    "suggested_title": "feat(ui): add homepage hero banner",
                    "summary": "Adds hero banner to homepage UI.",
                    "change_ids": ["hunk_1_home"],
                    "reasoning": "Independent frontend UI modification.",
                    "confidence": 0.96,
                    "uncertainty_flags": [],
                },
                {
                    "group_id": "group_4",
                    "suggested_title": "docs: update installation instructions",
                    "summary": "Updates README documentation.",
                    "change_ids": ["hunk_1_readme"],
                    "reasoning": "Documentation only.",
                    "confidence": 0.98,
                    "uncertainty_flags": [],
                },
            ],
            "ungrouped_changes": [],
            "warnings": [],
            "requires_manual_review": False,
        })

        mock_client = MagicMock(spec=OllamaClient)
        mock_client.default_model = "qwen3.5:4b"
        mock_client.chat.return_value = (expected_llm_json, 1.5)

        grouper = ChangeGrouper(client=mock_client)
        result = grouper.group_changes(complex_repo_changes)

        assert len(result.proposed_groups) == 4

        # Group 1 has cross-file hunks (auth.py hunk 1 + middleware.py)
        g1 = result.proposed_groups[0]
        assert "hunk_1_auth" in g1.change_ids
        assert "hunk_1_middleware" in g1.change_ids

        # Group 2 has hunk 2 of auth.py separated from hunk 1!
        g2 = result.proposed_groups[1]
        assert "hunk_2_auth_logging" in g2.change_ids
        assert "hunk_1_auth" not in g2.change_ids

        # Group 3 is independent UI
        g3 = result.proposed_groups[2]
        assert g3.change_ids == ["hunk_1_home"]

        # Group 4 is docs
        g4 = result.proposed_groups[3]
        assert g4.change_ids == ["hunk_1_readme"]

    def test_sensitive_file_excluded_generates_warning(self):
        repo_info = RepositoryInfo(root_path="/app")
        hunk_env = DiffHunk(hunk_id="h_env", source_state="staged", content="KEY=VAL")
        fc_env = FileChange(file_path=".env", hunks=[hunk_env], is_staged=True)

        hunk_code = DiffHunk(hunk_id="h_code", source_state="unstaged", content="x = 1")
        fc_code = FileChange(file_path="main.py", hunks=[hunk_code], is_unstaged=True)

        repo_changes = RepositoryChanges(
            repository=repo_info,
            changes=[fc_env, fc_code],
            total_files=2,
        )

        llm_json = json.dumps({
            "analysis_summary": "main.py update",
            "change_analyses": [
                {
                    "change_id": "h_code",
                    "file_path": "main.py",
                    "source_state": "unstaged",
                    "summary": "Update main logic",
                    "purpose": "Refactoring",
                    "affected_functionality": "Core",
                    "confidence": 0.95,
                    "uncertainty_reason": None,
                }
            ],
            "proposed_groups": [
                {
                    "group_id": "g1",
                    "suggested_title": "refactor: update main",
                    "summary": "main update",
                    "change_ids": ["h_code"],
                    "reasoning": "code change",
                    "confidence": 0.9,
                }
            ],
            "ungrouped_changes": [],
            "warnings": [],
        })

        mock_client = MagicMock(spec=OllamaClient)
        mock_client.default_model = "qwen3.5:4b"
        mock_client.chat.return_value = (llm_json, 1.0)

        grouper = ChangeGrouper(client=mock_client)
        result = grouper.group_changes(repo_changes)

        # Sensitive file .env must be excluded and warned
        assert any(".env" in w for w in result.warnings)
        assert len(result.proposed_groups) == 1
        assert result.proposed_groups[0].change_ids == ["h_code"]
