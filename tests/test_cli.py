"""Tests for CLI startup and output formatting."""

from unittest.mock import MagicMock, patch
import pytest

from main import main


def test_cli_startup_with_missing_ollama(capsys):
    """Verify CLI startup and output when Ollama is not running."""
    with patch("requests.get", side_effect=Exception("Connection error")):
        exit_code = main()
        assert exit_code == 0

        captured = capsys.readouterr().out
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

        captured = capsys.readouterr().out
        assert "COMMIT SURGEON" in captured
        assert "- Python: Installed" in captured
        assert "- Git: Installed" in captured
        assert "- Ollama: Running" in captured
        assert "- Local Model: Available" in captured
        assert "Project Status: Environment Check Complete" in captured
