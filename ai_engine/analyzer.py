"""AI change analysis and grouping engine using Ollama and Qwen3.5:4B."""

import json
from typing import Optional, Tuple
from pydantic import ValidationError

from config.settings import Settings, get_settings
from ai_engine.exceptions import (
    AIAnalysisError,
    GroupingValidationError,
    OllamaClientError,
    OllamaResponseError,
)
from ai_engine.models import GroupingResult, PreparedChangeContext
from ai_engine.ollama_client import OllamaClient
from ai_engine.prompts import (
    build_analysis_and_grouping_messages,
    build_repair_prompt,
)
from ai_engine.validator import GroupValidator


def extract_json_payload(raw_text: str) -> str:
    """Strip markdown code fence wrappers from model output if present."""
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[len("```json"):].strip()
    elif text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


class AIChangeAnalyzer:
    """Analyzes discrete repository changes and groups them using local LLM inference."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        validator: Optional[GroupValidator] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.client = client or OllamaClient(settings=self.settings)
        self.validator = validator or GroupValidator()

    def analyze_and_group(self, context: PreparedChangeContext) -> GroupingResult:
        """Execute LLM inference on prepared change context, validate, and return GroupingResult.

        Raises:
            AIAnalysisError: If inference fails or cannot be validated after repair.
            GroupingValidationError: If grouping structure is invalid.
        """
        if not context.items:
            # Clean repository or no eligible changes
            return GroupingResult(
                analysis_summary="No changes detected in repository context.",
                change_analyses=[],
                proposed_groups=[],
                ungrouped_changes=[],
                warnings=[],
                requires_manual_review=False,
                model_name=getattr(self.client, "default_model", "unknown"),
                inference_duration_seconds=0.0,
            )

        messages = build_analysis_and_grouping_messages(context)

        # First inference attempt
        raw_output, elapsed = self.client.chat(
            messages=messages,
            format_json=True,
            temperature=self.settings.ai_temperature,
        )

        try:
            cleaned_json = extract_json_payload(raw_output)
            result = GroupingResult.model_validate_json(cleaned_json)
            result.model_name = self.client.default_model
            result.inference_duration_seconds = elapsed
            self.validator.validate(result, context)
            return result
        except (ValidationError, GroupingValidationError, json.JSONDecodeError) as initial_err:
            # Allow at most one controlled repair attempt
            repair_messages = build_repair_prompt(
                previous_response=raw_output,
                error_message=str(initial_err),
                valid_change_ids=context.change_ids,
            )

            try:
                repair_output, repair_elapsed = self.client.chat(
                    messages=repair_messages,
                    format_json=True,
                    temperature=0.1,
                )
                cleaned_repair = extract_json_payload(repair_output)
                repaired_result = GroupingResult.model_validate_json(cleaned_repair)
                repaired_result.model_name = self.client.default_model
                repaired_result.inference_duration_seconds = elapsed + repair_elapsed
                repaired_result.warnings.append("Output required a repair cycle due to initial validation error.")
                self.validator.validate(repaired_result, context)
                return repaired_result
            except Exception as repair_err:
                raise AIAnalysisError(
                    f"AI grouping failed initial validation ({initial_err}) and repair attempt also failed: {repair_err}"
                ) from repair_err
