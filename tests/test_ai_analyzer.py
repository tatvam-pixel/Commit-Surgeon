"""Unit tests for AIChangeAnalyzer inference and repair flow."""

import json
from unittest.mock import MagicMock
import pytest

from ai_engine.analyzer import AIChangeAnalyzer, extract_json_payload
from ai_engine.exceptions import AIAnalysisError
from ai_engine.models import (
    ChangeContextItem,
    GroupingResult,
    PreparedChangeContext,
    ProposedCommitGroup,
)
from ai_engine.ollama_client import OllamaClient


@pytest.fixture
def test_context():
    return PreparedChangeContext(
        items=[
            ChangeContextItem(
                change_id="h1",
                file_path="src/login.py",
                source_state="staged",
                diff_content="+def login(): pass",
            ),
            ChangeContextItem(
                change_id="h2",
                file_path="tests/test_login.py",
                source_state="staged",
                diff_content="+def test_login(): pass",
            ),
        ]
    )


class TestExtractJsonPayload:
    """Test JSON cleaning utility."""

    def test_plain_json(self):
        assert extract_json_payload('{"key": "value"}') == '{"key": "value"}'

    def test_json_with_code_fences(self):
        raw = "```json\n{\"key\": \"value\"}\n```"
        assert extract_json_payload(raw) == '{"key": "value"}'

    def test_json_with_generic_code_fences(self):
        raw = "```\n{\"key\": \"value\"}\n```"
        assert extract_json_payload(raw) == '{"key": "value"}'


class TestAIChangeAnalyzerFlow:
    """Test analyzer invocation, parsing, and repair loops."""

    def test_empty_context_returns_empty_result_without_calling_llm(self):
        mock_client = MagicMock(spec=OllamaClient)
        analyzer = AIChangeAnalyzer(client=mock_client)

        empty_ctx = PreparedChangeContext(items=[])
        res = analyzer.analyze_and_group(empty_ctx)

        assert mock_client.chat.call_count == 0
        assert len(res.proposed_groups) == 0
        assert "No changes detected" in res.analysis_summary

    def test_successful_single_pass_analysis(self, test_context):
        valid_response_dict = {
            "analysis_summary": "Implemented login and tests",
            "change_analyses": [
                {
                    "change_id": "h1",
                    "file_path": "src/login.py",
                    "source_state": "staged",
                    "summary": "login",
                    "purpose": "login",
                    "affected_functionality": "login",
                    "confidence": 0.95,
                    "uncertainty_reason": None,
                },
                {
                    "change_id": "h2",
                    "file_path": "tests/test_login.py",
                    "source_state": "staged",
                    "summary": "test",
                    "purpose": "test",
                    "affected_functionality": "login test",
                    "confidence": 0.95,
                    "uncertainty_reason": None,
                },
            ],
            "proposed_groups": [
                {
                    "group_id": "group_1",
                    "suggested_title": "feat(auth): implement login with unit tests",
                    "summary": "Implements login method and accompanying tests",
                    "change_ids": ["h1", "h2"],
                    "reasoning": "Both changes relate to login authentication",
                    "confidence": 0.95,
                    "uncertainty_flags": [],
                }
            ],
            "ungrouped_changes": [],
            "warnings": [],
            "requires_manual_review": False,
        }

        mock_client = MagicMock(spec=OllamaClient)
        mock_client.default_model = "qwen3.5:4b"
        mock_client.chat.return_value = (f"```json\n{json.dumps(valid_response_dict)}\n```", 1.25)

        analyzer = AIChangeAnalyzer(client=mock_client)
        result = analyzer.analyze_and_group(test_context)

        assert mock_client.chat.call_count == 1
        assert len(result.proposed_groups) == 1
        assert result.proposed_groups[0].group_id == "group_1"
        assert result.inference_duration_seconds == 1.25
        assert result.model_name == "qwen3.5:4b"

    def test_repair_attempt_recovers_from_initial_malformed_response(self, test_context):
        # 1st call returns missing change_id (only h1)
        invalid_first_response = json.dumps({
            "analysis_summary": "incomplete",
            "proposed_groups": [
                {
                    "group_id": "group_1",
                    "suggested_title": "feat(login): login",
                    "summary": "login",
                    "change_ids": ["h1"],  # h2 is missing!
                    "reasoning": "reason",
                    "confidence": 0.9,
                }
            ],
        })

        # 2nd call fixes it (including change_analyses for h1 and h2)
        valid_repaired_response = json.dumps({
            "analysis_summary": "complete",
            "change_analyses": [
                {
                    "change_id": "h1",
                    "file_path": "src/login.py",
                    "source_state": "staged",
                    "summary": "login",
                    "purpose": "login",
                    "affected_functionality": "login",
                    "confidence": 0.95,
                    "uncertainty_reason": None,
                },
                {
                    "change_id": "h2",
                    "file_path": "tests/test_login.py",
                    "source_state": "staged",
                    "summary": "test",
                    "purpose": "test",
                    "affected_functionality": "login test",
                    "confidence": 0.95,
                    "uncertainty_reason": None,
                },
            ],
            "proposed_groups": [
                {
                    "group_id": "group_1",
                    "suggested_title": "feat(login): login and tests",
                    "summary": "login",
                    "change_ids": ["h1", "h2"],
                    "reasoning": "reason",
                    "confidence": 0.95,
                }
            ],
            "ungrouped_changes": [],
            "warnings": [],
        })

        mock_client = MagicMock(spec=OllamaClient)
        mock_client.default_model = "qwen3.5:4b"
        mock_client.chat.side_effect = [
            (invalid_first_response, 1.0),
            (valid_repaired_response, 0.8),
        ]

        analyzer = AIChangeAnalyzer(client=mock_client)
        result = analyzer.analyze_and_group(test_context)

        assert mock_client.chat.call_count == 2
        assert len(result.proposed_groups) == 1
        assert result.proposed_groups[0].change_ids == ["h1", "h2"]
        assert any("repair" in w for w in result.warnings)

    def test_repair_failure_raises_ai_analysis_error(self, test_context):
        # Both calls return invalid json
        mock_client = MagicMock(spec=OllamaClient)
        mock_client.default_model = "qwen3.5:4b"
        mock_client.chat.side_effect = [
            ("this is not json", 1.0),
            ("still not json", 0.5),
        ]

        analyzer = AIChangeAnalyzer(client=mock_client)
        with pytest.raises(AIAnalysisError, match="AI grouping failed initial validation"):
            analyzer.analyze_and_group(test_context)
