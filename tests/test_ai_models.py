"""Unit tests for AI engine Pydantic models and context preparation."""

import pytest
from pydantic import ValidationError

from ai_engine.context import is_sensitive_file, prepare_change_context
from ai_engine.exceptions import ContextExceededLimitError
from ai_engine.models import (
    ChangeAnalysis,
    ChangeContextItem,
    GroupingResult,
    PreparedChangeContext,
    ProposedCommitGroup,
)
from git_engine.models import DiffHunk, FileChange, RepositoryChanges, RepositoryInfo


class TestAIModelsValidation:
    """Test validation constraints on AI models."""

    def test_valid_change_analysis(self):
        ca = ChangeAnalysis(
            change_id="h1",
            file_path="src/auth.py",
            source_state="staged",
            summary="Fix auth bug",
            purpose="Ensure valid token check",
            affected_functionality="Authentication",
            confidence=0.95,
        )
        assert ca.confidence == 0.95
        assert ca.uncertainty_reason is None

    def test_change_analysis_invalid_confidence_raises(self):
        with pytest.raises(ValidationError):
            ChangeAnalysis(
                change_id="h1",
                file_path="src/auth.py",
                source_state="staged",
                summary="Fix auth bug",
                purpose="Ensure token check",
                affected_functionality="Auth",
                confidence=1.5,
            )

        with pytest.raises(ValidationError):
            ChangeAnalysis(
                change_id="h1",
                file_path="src/auth.py",
                source_state="staged",
                summary="Fix auth bug",
                purpose="Ensure token check",
                affected_functionality="Auth",
                confidence=-0.1,
            )

    def test_valid_proposed_commit_group(self):
        group = ProposedCommitGroup(
            group_id="group_1",
            suggested_title="fix(auth): correct token validation",
            summary="Patches JWT expiration check",
            change_ids=["h1", "h2"],
            reasoning="Both hunks relate to token verification",
            confidence=0.9,
            uncertainty_flags=[],
        )
        assert len(group.change_ids) == 2
        assert group.confidence == 0.9

    def test_proposed_group_invalid_confidence_raises(self):
        with pytest.raises(ValidationError):
            ProposedCommitGroup(
                group_id="group_1",
                suggested_title="feat: test",
                summary="test",
                change_ids=["h1"],
                reasoning="test",
                confidence=1.2,
            )

    def test_valid_grouping_result(self):
        res = GroupingResult(
            analysis_summary="Summary of work",
            change_analyses=[],
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="docs: update readme",
                    summary="Updates readme",
                    change_ids=["h_readme"],
                    reasoning="Documentation",
                    confidence=0.99,
                )
            ],
            ungrouped_changes=[],
            warnings=[],
            requires_manual_review=False,
        )
        assert len(res.proposed_groups) == 1
        assert res.requires_manual_review is False


class TestSensitiveFileFiltering:
    """Test sensitive file identification and context sanitization."""

    def test_is_sensitive_file(self):
        assert is_sensitive_file(".env") is True
        assert is_sensitive_file(".env.local") is True
        assert is_sensitive_file("config/.env.prod") is True
        assert is_sensitive_file("id_rsa") is True
        assert is_sensitive_file("cert.pem") is True
        assert is_sensitive_file("secrets.yaml") is True
        assert is_sensitive_file("wp-config.php") is True
        assert is_sensitive_file("client_secret.json") is True

        assert is_sensitive_file("main.py") is False
        assert is_sensitive_file("src/auth.py") is False
        assert is_sensitive_file("README.md") is False

    def test_prepare_change_context_excludes_sensitive_files(self):
        repo_info = RepositoryInfo(root_path="/repo")
        hunk1 = DiffHunk(hunk_id="h_env", source_state="staged", content="SECRET=12345")
        fc_env = FileChange(file_path=".env", hunks=[hunk1], is_staged=True)

        hunk2 = DiffHunk(hunk_id="h_code", source_state="staged", content="print('hello')")
        fc_code = FileChange(file_path="main.py", hunks=[hunk2], is_staged=True)

        repo_changes = RepositoryChanges(
            repository=repo_info,
            changes=[fc_env, fc_code],
            total_files=2,
        )

        ctx = prepare_change_context(repo_changes)
        assert ".env" in ctx.excluded_files
        assert "h_env" not in ctx.change_ids
        assert "h_code" in ctx.change_ids
        assert len(ctx.items) == 1

    def test_prepare_change_context_truncated_input_raises(self):
        repo_info = RepositoryInfo(root_path="/repo")
        repo_changes = RepositoryChanges(
            repository=repo_info,
            changes=[],
            has_truncated_content=True,
        )
        with pytest.raises(ContextExceededLimitError, match="truncated due to repository size"):
            prepare_change_context(repo_changes)
