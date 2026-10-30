"""Tests for CLI startup and output formatting."""

import re
from unittest.mock import MagicMock, patch
import pytest

from main import main


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences to make string assertions robust in all environments."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def test_cli_startup_with_missing_ollama(capsys):
    """Verify CLI startup and output when Ollama is not running."""
    with patch("requests.get", side_effect=Exception("Connection error")):
        exit_code = main()
        assert exit_code == 0

        captured = _strip_ansi(capsys.readouterr().out)
        assert "COMMIT SURGEON" in captured
        assert "AI-powered offline Git commit management" in captured
        assert "Version: 0.1.0" in captured
        assert "Environment Status:" in captured
        assert "- Python: Installed" in captured
        assert "- Git: Installed" in captured
        assert "- Ollama: Not Running" in captured
        assert "- Local Model: Unknown" in captured
        assert "Project Status: Environment Check Complete" in captured
        assert "ollama serve" in captured
        assert "ollama pull qwen3.5:4b" in captured


def test_cli_startup_all_ready(capsys):
    """Verify CLI output when all services and models are available."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [{"name": "qwen3.5:4b"}]
    }

    with patch("requests.get", return_value=mock_response):
        exit_code = main()
        assert exit_code == 0

        captured = _strip_ansi(capsys.readouterr().out)
        assert "COMMIT SURGEON" in captured
        assert "- Python: Installed" in captured
        assert "- Git: Installed" in captured
        assert "- Ollama: Running" in captured
        assert "- Local Model: Available" in captured
        assert "Project Status: Environment Check Complete" in captured


def test_cli_group_when_ollama_not_running(capsys):
    """Verify group CLI reports error when Ollama is offline."""
    with patch("ai_engine.ollama_client.OllamaClient.is_service_running", return_value=False):
        exit_code = main(["group"])
        assert exit_code == 1
        captured = _strip_ansi(capsys.readouterr().out)
        assert "Ollama is not running" in captured
        assert "ollama serve" in captured


def test_cli_group_when_model_missing(capsys):
    """Verify group CLI reports error when model is not downloaded."""
    with patch("ai_engine.ollama_client.OllamaClient.is_service_running", return_value=True), \
         patch("ai_engine.ollama_client.OllamaClient.is_model_available", return_value=False):
        exit_code = main(["group"])
        assert exit_code == 1
        captured = _strip_ansi(capsys.readouterr().out)
        assert "not available locally in Ollama" in captured
        assert "ollama pull qwen3.5:4b" in captured


def test_cli_group_success_display(capsys):
    """Verify group CLI displays proposed groups and formatting."""
    from ai_engine.models import GroupingResult, ProposedCommitGroup
    from git_engine.models import DiffHunk, FileChange, RepositoryChanges, RepositoryInfo

    fake_hunk = DiffHunk(hunk_id="h1_auth", source_state="staged", added_lines=1)
    fake_fc = FileChange(file_path="auth.py", hunks=[fake_hunk], is_staged=True)
    fake_changes = RepositoryChanges(
        repository=RepositoryInfo(root_path="c:/test/repo", current_branch="main"),
        changes=[fake_fc],
        total_files=1,
    )

    fake_result = GroupingResult(
        analysis_summary="Analysis complete",
        proposed_groups=[
            ProposedCommitGroup(
                group_id="group_1",
                suggested_title="fix(auth): update login validation",
                summary="Fixes login return value",
                change_ids=["h1_auth"],
                reasoning="These changes implement the authentication workflow.",
                confidence=0.92,
            )
        ],
        ungrouped_changes=[],
        warnings=[],
    )

    with patch("ai_engine.ollama_client.OllamaClient.is_service_running", return_value=True), \
         patch("ai_engine.ollama_client.OllamaClient.is_model_available", return_value=True), \
         patch("main.analyze_repository", return_value=fake_changes), \
         patch("ai_engine.grouper.ChangeGrouper.group_changes", return_value=fake_result):

        exit_code = main(["group"])
        assert exit_code == 0
        captured = _strip_ansi(capsys.readouterr().out)
        assert "COMMIT SURGEON" in captured
        assert "AI Change Grouping" in captured
        assert "Group 1: fix(auth): update login validation" in captured
        assert "Files:\n- auth.py" in captured
        assert "Reason:\nThese changes implement the authentication workflow." in captured
        assert "Confidence: 0.92" in captured
        assert "Analysis completed." in captured
