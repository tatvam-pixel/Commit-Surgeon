"""Pydantic v2 data models for AI change analysis and grouping."""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ChangeContextItem(BaseModel):
    """Represents a discrete, sanitized change item supplied as context to the LLM."""

    change_id: str = Field(description="Unique identifier for the hunk or change unit")
    file_path: str = Field(description="Relative path of the modified file")
    source_state: str = Field(description="Source state: 'staged', 'unstaged', or 'untracked'")
    change_type: str = Field(default="modified", description="Type of change: modified, added, deleted, renamed, untracked")
    added_lines: int = Field(default=0, description="Count of added lines")
    deleted_lines: int = Field(default=0, description="Count of deleted lines")
    header: str = Field(default="", description="Diff hunk header, e.g. @@ ... @@")
    diff_content: str = Field(default="", description="Sanitized diff lines for this change")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }


class PreparedChangeContext(BaseModel):
    """Context container prepared from RepositoryChanges for LLM ingestion."""

    items: List[ChangeContextItem] = Field(default_factory=list, description="List of change units")
    total_chars: int = Field(default=0, description="Total character count of the context")
    excluded_files: List[str] = Field(default_factory=list, description="Sensitive or excluded files omitted")
    is_truncated: bool = Field(default=False, description="True if input had truncation or limit hit")
    repository_name: str = Field(default="", description="Name of repository")
    repository_branch: Optional[str] = Field(default=None, description="Active branch name")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }

    @property
    def change_ids(self) -> List[str]:
        """List of all change IDs in the prepared context."""
        return [item.change_id for item in self.items]


class ChangeAnalysis(BaseModel):
    """Semantic analysis of an individual change unit produced by LLM."""

    change_id: str = Field(description="Identifier of the change unit analyzed")
    file_path: str = Field(description="Path of the file affected")
    source_state: str = Field(description="Source state: 'staged', 'unstaged', or 'untracked'")
    summary: str = Field(description="Concise description of what changed")
    purpose: str = Field(description="Apparent objective or intent of the change")
    affected_functionality: str = Field(description="Subsystem, module, or feature affected")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    uncertainty_reason: Optional[str] = Field(default=None, description="Reason if confidence is low or intent is ambiguous")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is clamped between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {v}")
        return v


class ProposedCommitGroup(BaseModel):
    """A logical cluster of related changes proposed as a single atomic commit."""

    group_id: str = Field(description="Unique group identifier, e.g. 'group_1'")
    suggested_title: str = Field(description="Concise suggested commit summary, preferably Conventional Commit style")
    summary: str = Field(description="Explanation of the group's cohesive purpose")
    change_ids: List[str] = Field(default_factory=list, description="List of change_ids included in this group")
    reasoning: str = Field(description="Justification for grouping these specific changes together")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    uncertainty_flags: List[str] = Field(default_factory=list, description="Flags for ambiguous or loose couplings")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is clamped between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {v}")
        return v


class GroupingResult(BaseModel):
    """Complete structured output containing change analyses and proposed commit groups."""

    analysis_summary: str = Field(description="High-level overview of detected repository modifications")
    change_analyses: List[ChangeAnalysis] = Field(default_factory=list, description="Per-change semantic analysis")
    proposed_groups: List[ProposedCommitGroup] = Field(default_factory=list, description="Proposed logical commit groups")
    ungrouped_changes: List[str] = Field(default_factory=list, description="Change IDs that could not be grouped with confidence")
    warnings: List[str] = Field(default_factory=list, description="Warnings generated during analysis or validation")
    requires_manual_review: bool = Field(default=False, description="True if ambiguities or low confidence require user review")
    model_name: Optional[str] = Field(default=None, description="Local LLM model name used for inference")
    inference_duration_seconds: Optional[float] = Field(default=None, description="Elapsed wall-clock time for LLM inference")

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }
