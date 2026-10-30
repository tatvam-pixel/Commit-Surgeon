"""Tests for conflict blocking, binary attribution, and analysis validation (P1 #2, P2 #3, P2 #5)."""

import pytest
from unittest.mock import MagicMock, patch

from ai_engine.context import prepare_change_context
from ai_engine.exceptions import (
    ContextPreparationError,
    DuplicateChangeError,
    MissingChangeIdError,
)
from ai_engine.models import (
    ChangeAnalysis,
    ChangeContextItem,
    GroupingResult,
    PreparedChangeContext,
    ProposedCommitGroup,
)
from ai_engine.validator import GroupValidator
from config.settings import Settings
from git_engine.models import DiffHunk, FileChange, RepositoryChanges, RepositoryInfo
from main import main


class TestMergeConflictBlocking:
    """Fix #2: Block AI grouping when merge conflicts exist."""

    def _make_changes(self, has_conflicts=False, change_type="modified"):
        repo = RepositoryInfo(root_path="/test/repo", current_branch="main")
        fc = FileChange(
            file_path="conflict.py",
            change_type=change_type,
            is_staged=True,
            hunks=[DiffHunk(hunk_id="h1", source_state="staged", added_lines=1)],
        )
        return RepositoryChanges(
            repository=repo,
            changes=[fc],
            total_files=1,
            has_conflicts=has_conflicts,
        )

    def test_conflicts_block_context_preparation(self):
        changes = self._make_changes(has_conflicts=True, change_type="conflicted")
        settings = Settings()
        with pytest.raises(ContextPreparationError, match="merge conflicts"):
            prepare_change_context(changes, settings=settings)

    def test_no_conflicts_allows_context_preparation(self):
        changes = self._make_changes(has_conflicts=False)
        settings = Settings()
        ctx = prepare_change_context(changes, settings=settings)
        assert len(ctx.items) == 1

    def test_cli_group_with_conflicts_shows_error(self, capsys):
        changes = self._make_changes(has_conflicts=True, change_type="conflicted")
        with patch("ai_engine.ollama_client.OllamaClient.is_service_running", return_value=True), \
             patch("ai_engine.ollama_client.OllamaClient.is_model_available", return_value=True), \
             patch("main.analyze_repository", return_value=changes):
            exit_code = main(["group"])
            assert exit_code == 1
            captured = capsys.readouterr().out
            assert "conflict" in captured.lower() or "Conflict" in captured


class TestBinarySourceAttribution:
    """Fix #3: Binary file source_state should include 'untracked'."""

    def _make_binary_fc(self, is_staged=False, is_unstaged=False, is_untracked=False):
        return FileChange(
            file_path="image.png",
            change_type="added" if is_untracked else "modified",
            is_binary=True,
            is_staged=is_staged,
            is_unstaged=is_unstaged,
            is_untracked=is_untracked,
        )

    def test_staged_binary_attribution(self):
        fc = self._make_binary_fc(is_staged=True)
        changes = RepositoryChanges(
            repository=RepositoryInfo(root_path="/test/repo"),
            changes=[fc],
            total_files=1,
        )
        ctx = prepare_change_context(changes, settings=Settings())
        assert ctx.items[0].source_state == "staged"

    def test_unstaged_binary_attribution(self):
        fc = self._make_binary_fc(is_unstaged=True)
        changes = RepositoryChanges(
            repository=RepositoryInfo(root_path="/test/repo"),
            changes=[fc],
            total_files=1,
        )
        ctx = prepare_change_context(changes, settings=Settings())
        assert ctx.items[0].source_state == "unstaged"

    def test_untracked_binary_attribution(self):
        fc = self._make_binary_fc(is_untracked=True, is_unstaged=True)
        changes = RepositoryChanges(
            repository=RepositoryInfo(root_path="/test/repo"),
            changes=[fc],
            total_files=1,
        )
        ctx = prepare_change_context(changes, settings=Settings())
        assert ctx.items[0].source_state == "untracked"


class TestAnalysisValidationCompleteness:
    """Fix #5: ChangeAnalysis completeness and uniqueness validation."""

    def _make_context_and_result(self, change_ids, analysis_ids, group_ids=None):
        items = [
            ChangeContextItem(
                change_id=cid,
                file_path="test.py",
                source_state="staged",
                diff_content="some diff",
            )
            for cid in change_ids
        ]
        ctx = PreparedChangeContext(items=items, total_chars=100)

        analyses = [
            ChangeAnalysis(
                change_id=aid,
                file_path="test.py",
                source_state="staged",
                summary="test",
                purpose="test",
                affected_functionality="test",
                confidence=0.9,
            )
            for aid in analysis_ids
        ]

        if group_ids is None:
            group_ids = change_ids

        result = GroupingResult(
            analysis_summary="test",
            change_analyses=analyses,
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="test",
                    summary="test",
                    change_ids=list(group_ids),
                    reasoning="test",
                    confidence=0.9,
                )
            ],
        )
        return ctx, result

    def test_complete_analysis_passes(self):
        ctx, result = self._make_context_and_result(
            ["h1", "h2"], ["h1", "h2"]
        )
        validator = GroupValidator()
        warnings = validator.validate(result, ctx)
        # Should not raise

    def test_duplicate_analysis_raises(self):
        ctx, result = self._make_context_and_result(
            ["h1", "h2"], ["h1", "h1", "h2"]
        )
        validator = GroupValidator()
        with pytest.raises(DuplicateChangeError, match="Duplicate ChangeAnalysis"):
            validator.validate(result, ctx)

    def test_missing_analysis_raises(self):
        ctx, result = self._make_context_and_result(
            ["h1", "h2", "h3"], ["h1", "h2"], group_ids=["h1", "h2", "h3"]
        )
        validator = GroupValidator()
        with pytest.raises(MissingChangeIdError, match="Missing ChangeAnalysis"):
            validator.validate(result, ctx)

    def test_empty_analysis_list_with_non_empty_input_raises(self):
        """When input changes exist, an empty analyses list must be rejected."""
        ctx, result = self._make_context_and_result(["h1", "h2"], [])
        validator = GroupValidator()
        with pytest.raises(MissingChangeIdError, match="Missing ChangeAnalysis"):
            validator.validate(result, ctx)

    def test_unknown_analysis_raises(self):
        """ChangeAnalysis referencing non-existent change_id must be rejected."""
        from ai_engine.exceptions import UnknownChangeIdError
        ctx, result = self._make_context_and_result(["h1"], ["h1", "h_ghost"])
        validator = GroupValidator()
        with pytest.raises(UnknownChangeIdError, match="unknown change_id"):
            validator.validate(result, ctx)

    def test_invalid_confidence_in_analysis_raises(self):
        """ChangeAnalysis with confidence outside [0.0, 1.0] must be rejected."""
        from ai_engine.exceptions import InvalidConfidenceError
        from ai_engine.models import ChangeAnalysis
        ctx, result = self._make_context_and_result(["h1"], ["h1"])
        # Bypass pydantic model validator to test business logic validator
        result.change_analyses[0].__dict__["confidence"] = 1.5
        validator = GroupValidator()
        with pytest.raises(InvalidConfidenceError, match="invalid confidence"):
            validator.validate(result, ctx)

    def test_incorrect_source_state_in_analysis_raises(self):
        """ChangeAnalysis with mismatched source_state must be rejected."""
        from ai_engine.exceptions import SourceStateMismatchError
        ctx, result = self._make_context_and_result(["h1"], ["h1"])
        # In context, h1 is staged; set analysis to unstaged
        result.change_analyses[0].source_state = "unstaged"
        validator = GroupValidator()
        with pytest.raises(SourceStateMismatchError, match="source_state"):
            validator.validate(result, ctx)
