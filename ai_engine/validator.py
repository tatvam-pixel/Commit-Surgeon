"""Validation engine for AI-generated change analyses and commit groups."""

from typing import Dict, List, Set
from ai_engine.exceptions import (
    CoverageValidationError,
    DuplicateChangeError,
    EmptyGroupError,
    GroupingValidationError,
    InvalidConfidenceError,
    MissingChangeIdError,
    SourceStateMismatchError,
    UnknownChangeIdError,
)
from ai_engine.models import GroupingResult, PreparedChangeContext


class GroupValidator:
    """Strict validator for LLM-generated commit groups and analyses."""

    def validate(
        self,
        result: GroupingResult,
        context: PreparedChangeContext,
    ) -> List[str]:
        """Validate that GroupingResult strictly adheres to all grouping invariants.

        Returns:
            List of non-fatal warning messages.

        Raises:
            EmptyGroupError: If any proposed group has 0 changes.
            UnknownChangeIdError: If change_id not in context is referenced.
            DuplicateChangeError: If a change_id appears in multiple groups or ungrouped.
            MissingChangeIdError: If an input change_id is omitted.
            CoverageValidationError: If input change coverage is incomplete.
            InvalidConfidenceError: If any confidence score is outside [0.0, 1.0].
            SourceStateMismatchError: If change analysis has incorrect source_state.
        """
        warnings: List[str] = []
        input_ids: Set[str] = set(context.change_ids)
        input_items_by_id = {item.change_id: item for item in context.items}

        # 1. Truncation / Completeness Check
        if context.is_truncated:
            warnings.append("Input context was marked as truncated; grouping may be incomplete.")
            result.requires_manual_review = True

        # 2. Check Empty Groups & Confidence Scores
        seen_grouped_ids: Set[str] = set()

        for group in result.proposed_groups:
            if not group.change_ids:
                raise EmptyGroupError(f"Proposed group '{group.group_id}' contains no changes.")

            if not (0.0 <= group.confidence <= 1.0):
                raise InvalidConfidenceError(
                    f"Group '{group.group_id}' has invalid confidence {group.confidence}. Must be in [0.0, 1.0]."
                )

            if group.confidence < 0.7:
                warnings.append(
                    f"Group '{group.group_id}' has low confidence ({group.confidence:.2f}): {group.reasoning}"
                )
                result.requires_manual_review = True

            for cid in group.change_ids:
                # 3. Check Unknown IDs
                if cid not in input_ids:
                    raise UnknownChangeIdError(
                        f"Proposed group '{group.group_id}' contains unknown change_id: '{cid}'"
                    )

                # 4. Check Duplicate Change IDs across groups
                if cid in seen_grouped_ids:
                    raise DuplicateChangeError(
                        f"Change '{cid}' appears in multiple groups or entries."
                    )
                seen_grouped_ids.add(cid)

        # 5. Check Ungrouped Changes
        for uid in result.ungrouped_changes:
            if uid not in input_ids:
                raise UnknownChangeIdError(f"Ungrouped changes contains unknown change_id: '{uid}'")
            if uid in seen_grouped_ids:
                raise DuplicateChangeError(
                    f"Change '{uid}' is present in both a proposed group and ungrouped_changes."
                )
            seen_grouped_ids.add(uid)

        # 6. Check Change Coverage (every input change accounted for exactly once)
        missing_ids = input_ids - seen_grouped_ids
        if missing_ids:
            raise MissingChangeIdError(
                f"Missing {len(missing_ids)} change(s) from grouping output: {sorted(list(missing_ids))}"
            )

        # 7. Check Individual Change Analyses completeness and integrity (unconditional)
        seen_analysis_ids: Set[str] = set()

        for ca in result.change_analyses:
            if ca.change_id not in input_ids:
                raise UnknownChangeIdError(
                    f"ChangeAnalysis contains unknown change_id: '{ca.change_id}'"
                )

            if ca.change_id in seen_analysis_ids:
                raise DuplicateChangeError(
                    f"Duplicate ChangeAnalysis for change_id: '{ca.change_id}'"
                )
            seen_analysis_ids.add(ca.change_id)

            if not (0.0 <= ca.confidence <= 1.0):
                raise InvalidConfidenceError(
                    f"ChangeAnalysis '{ca.change_id}' has invalid confidence {ca.confidence}."
                )

            # Source-state preservation check
            expected_item = input_items_by_id.get(ca.change_id)
            if expected_item and ca.source_state != expected_item.source_state:
                raise SourceStateMismatchError(
                    f"ChangeAnalysis '{ca.change_id}' source_state '{ca.source_state}' does not match "
                    f"input source_state '{expected_item.source_state}'"
                )

        # Enforce that every input change has exactly one analysis
        missing_analyses = input_ids - seen_analysis_ids
        if missing_analyses:
            raise MissingChangeIdError(
                f"Missing ChangeAnalysis for {len(missing_analyses)} change(s): "
                f"{sorted(list(missing_analyses))}"
            )

        if result.ungrouped_changes:
            warnings.append(
                f"{len(result.ungrouped_changes)} change(s) could not be grouped with confidence and remain ungrouped."
            )
            result.requires_manual_review = True

        result.warnings.extend(warnings)
        return warnings
