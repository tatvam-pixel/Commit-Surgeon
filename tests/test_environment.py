"""Tests for environment detection and verification."""

from unittest.mock import MagicMock, patch
import requests

from config.settings import Settings
from utils.environment import (
    check_git,
    check_local_model,
    check_ollama_service,
    check_python,
    run_environment_check,
)


def test_check_python():
    """Verify Python environment detection."""
    status = check_python()
    assert status.name == "Python"
    assert status.label == "Installed"
    assert status.is_ok is True
    assert "Python 3." in status.details


def test_check_git_installed():
    """Verify Git detection in current environment without repository modification."""
    status = check_git()
    assert status.name == "Git"
    assert status.label == "Installed"
    assert status.is_ok is True
    assert "git version" in status.details.lower()


def test_check_git_missing():
    """Verify Git detection when binary is not in PATH."""
    with patch("shutil.which", return_value=None):
        status = check_git()
        assert status.name == "Git"
        assert status.label == "Missing"
        assert status.is_ok is False
        assert "not found" in status.details.lower()


def test_check_ollama_service_running():
    """Verify Ollama detection when service returns HTTP 200."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("requests.get", return_value=mock_response):
        status = check_ollama_service("http://localhost:11434")
        assert status.name == "Ollama"
        assert status.label == "Running"
        assert status.is_ok is True


def test_check_ollama_service_not_running():
    """Verify Ollama detection when service is unreachable."""
    with patch("requests.get", side_effect=requests.RequestException("Connection refused")):
        status = check_ollama_service("http://localhost:11434")
        assert status.name == "Ollama"
        assert status.label == "Not Running"
        assert status.is_ok is False
        assert status.instructions is not None
        assert "ollama serve" in status.instructions


def test_check_local_model_when_ollama_not_running():
    """Verify model status is reported as UNKNOWN when Ollama is unavailable."""
    status = check_local_model(
        api_url="http://localhost:11434",
        model_name="qwen3.5:4b",
        ollama_running=False,
    )
    assert status.name == "Local Model"
    assert status.label == "Unknown"
    assert status.is_ok is False
    assert "ollama is not running" in status.details.lower()
    assert "ollama pull qwen3.5:4b" in status.instructions


def test_check_local_model_available():
    """Verify model detection when model is present in Ollama."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [
            {"name": "qwen3.5:4b", "size": 2500000000},
            {"name": "llama3.2:1b", "size": 1100000000},
        ]
    }

    with patch("requests.get", return_value=mock_response):
        status = check_local_model(
            api_url="http://localhost:11434",
            model_name="qwen3.5:4b",
            ollama_running=True,
        )
        assert status.name == "Local Model"
        assert status.label == "Available"
        assert status.is_ok is True
        assert "available locally" in status.details


def test_check_local_model_missing():
    """Verify model detection when model is missing from Ollama."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [{"name": "llama3.2:1b", "size": 1100000000}]
    }

    with patch("requests.get", return_value=mock_response):
        status = check_local_model(
            api_url="http://localhost:11434",
            model_name="qwen3.5:4b",
            ollama_running=True,
        )
        assert status.name == "Local Model"
        assert status.label == "Not Available"
        assert status.is_ok is False
        assert "ollama pull qwen3.5:4b" in status.instructions
        assert "4 billion parameters" in status.instructions


def test_check_local_model_query_error():
    """Verify model status is reported as UNKNOWN when querying Ollama fails."""
    with patch("requests.get", side_effect=Exception("Timeout reading models")):
        status = check_local_model(
            api_url="http://localhost:11434",
            model_name="qwen3.5:4b",
            ollama_running=True,
        )
        assert status.name == "Local Model"
        assert status.label == "Unknown"
        assert status.is_ok is False


def test_run_environment_check_all_ready():
    """Verify aggregated environment check when all components are available."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "models": [{"name": "qwen3.5:4b", "size": 2500000000}]
    }

    with patch("requests.get", return_value=mock_response):
        report = run_environment_check(
            settings=Settings(default_model="qwen3.5:4b"),
        )
        assert report.python.is_ok is True
        assert report.git.is_ok is True
        assert report.ollama.is_ok is True
        assert report.model.is_ok is True
        assert report.all_ready is True
