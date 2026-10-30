"""Unit tests for GroupValidator invariant enforcement."""

import pytest

from ai_engine.exceptions import (
    DuplicateChangeError,
    EmptyGroupError,
    InvalidConfidenceError,
    MissingChangeIdError,
    SourceStateMismatchError,
    UnknownChangeIdError,
)
from ai_engine.models import (
    ChangeAnalysis,
    ChangeContextItem,
    GroupingResult,
    PreparedChangeContext,
    ProposedCommitGroup,
)
from ai_engine.validator import GroupValidator


@pytest.fixture
def sample_context():
    return PreparedChangeContext(
        items=[
            ChangeContextItem(
                change_id="h_auth",
                file_path="auth.py",
                source_state="staged",
                diff_content="auth diff",
            ),
            ChangeContextItem(
                change_id="h_ui",
                file_path="home.py",
                source_state="unstaged",
                diff_content="ui diff",
            ),
        ]
    )


class TestGroupValidator:
    """Test group validator integrity checks."""

    def test_valid_complete_grouping(self, sample_context):
        validator = GroupValidator()
        result = GroupingResult(
            analysis_summary="Valid analysis",
            change_analyses=[
                ChangeAnalysis(
                    change_id="h_auth",
                    file_path="auth.py",
                    source_state="staged",
                    summary="auth update",
                    purpose="auth",
                    affected_functionality="auth",
                    confidence=0.9,
                ),
                ChangeAnalysis(
                    change_id="h_ui",
                    file_path="home.py",
                    source_state="unstaged",
                    summary="ui update",
                    purpose="ui",
                    affected_functionality="ui",
                    confidence=0.85,
                ),
            ],
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="fix(auth): update login",
                    summary="fixes login",
                    change_ids=["h_auth"],
                    reasoning="auth fixes",
                    confidence=0.9,
                ),
                ProposedCommitGroup(
                    group_id="g2",
                    suggested_title="feat(ui): update home page",
                    summary="ui changes",
                    change_ids=["h_ui"],
                    reasoning="ui fixes",
                    confidence=0.85,
                ),
            ],
            ungrouped_changes=[],
            warnings=[],
        )

        warnings = validator.validate(result, sample_context)
        assert len(warnings) == 0

    def test_empty_group_raises(self, sample_context):
        validator = GroupValidator()
        result = GroupingResult(
            analysis_summary="Test",
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="empty group",
                    summary="empty",
                    change_ids=[],
                    reasoning="none",
                    confidence=0.9,
                )
            ],
        )
        with pytest.raises(EmptyGroupError, match="contains no changes"):
            validator.validate(result, sample_context)

    def test_unknown_change_id_raises(self, sample_context):
        validator = GroupValidator()
        result = GroupingResult(
            analysis_summary="Test",
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="title",
                    summary="summary",
                    change_ids=["h_auth", "h_hallucinated"],
                    reasoning="reason",
                    confidence=0.9,
                )
            ],
            ungrouped_changes=["h_ui"],
        )
        with pytest.raises(UnknownChangeIdError, match="unknown change_id: 'h_hallucinated'"):
            validator.validate(result, sample_context)

    def test_duplicate_change_id_across_groups_raises(self, sample_context):
        validator = GroupValidator()
        result = GroupingResult(
            analysis_summary="Test",
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="title 1",
                    summary="summary 1",
                    change_ids=["h_auth"],
                    reasoning="reason 1",
                    confidence=0.9,
                ),
                ProposedCommitGroup(
                    group_id="g2",
                    suggested_title="title 2",
                    summary="summary 2",
                    change_ids=["h_auth", "h_ui"],
                    reasoning="reason 2",
                    confidence=0.8,
                ),
            ],
        )
        with pytest.raises(DuplicateChangeError, match="appears in multiple groups"):
            validator.validate(result, sample_context)

    def test_duplicate_change_in_group_and_ungrouped_raises(self, sample_context):
        validator = GroupValidator()
        result = GroupingResult(
            analysis_summary="Test",
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="title 1",
                    summary="summary 1",
                    change_ids=["h_auth"],
                    reasoning="reason 1",
                    confidence=0.9,
                )
            ],
            ungrouped_changes=["h_auth", "h_ui"],
        )
        with pytest.raises(DuplicateChangeError, match="present in both a proposed group and ungrouped"):
            validator.validate(result, sample_context)

    def test_missing_change_id_raises(self, sample_context):
        validator = GroupValidator()
        # Only h_auth covered, h_ui silently omitted
        result = GroupingResult(
            analysis_summary="Test",
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="title 1",
                    summary="summary 1",
                    change_ids=["h_auth"],
                    reasoning="reason 1",
                    confidence=0.9,
                )
            ],
            ungrouped_changes=[],
        )
        with pytest.raises(MissingChangeIdError, match="Missing 1 change.*h_ui"):
            validator.validate(result, sample_context)

    def test_source_state_mismatch_raises(self, sample_context):
        validator = GroupValidator()
        # h_auth is staged in context, but analysis reports unstaged
        result = GroupingResult(
            analysis_summary="Test",
            change_analyses=[
                ChangeAnalysis(
                    change_id="h_auth",
                    file_path="auth.py",
                    source_state="unstaged",  # MISMATCH
                    summary="auth",
                    purpose="auth",
                    affected_functionality="auth",
                    confidence=0.9,
                ),
                ChangeAnalysis(
                    change_id="h_ui",
                    file_path="home.py",
                    source_state="unstaged",
                    summary="ui",
                    purpose="ui",
                    affected_functionality="ui",
                    confidence=0.9,
                ),
            ],
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="title 1",
                    summary="summary 1",
                    change_ids=["h_auth", "h_ui"],
                    reasoning="reason 1",
                    confidence=0.9,
                )
            ],
        )
        with pytest.raises(SourceStateMismatchError, match="does not match input source_state"):
            validator.validate(result, sample_context)

    def test_low_confidence_generates_warning_and_review_flag(self, sample_context):
        validator = GroupValidator()
        result = GroupingResult(
            analysis_summary="Test",
            change_analyses=[
                ChangeAnalysis(
                    change_id="h_auth",
                    file_path="auth.py",
                    source_state="staged",
                    summary="auth update",
                    purpose="auth",
                    affected_functionality="auth",
                    confidence=0.9,
                ),
                ChangeAnalysis(
                    change_id="h_ui",
                    file_path="home.py",
                    source_state="unstaged",
                    summary="ui update",
                    purpose="ui",
                    affected_functionality="ui",
                    confidence=0.85,
                ),
            ],
            proposed_groups=[
                ProposedCommitGroup(
                    group_id="g1",
                    suggested_title="title 1",
                    summary="summary 1",
                    change_ids=["h_auth", "h_ui"],
                    reasoning="reason 1",
                    confidence=0.55,  # Low confidence
                )
            ],
        )
        warnings = validator.validate(result, sample_context)
        assert any("low confidence" in w for w in warnings)
        assert result.requires_manual_review is True
