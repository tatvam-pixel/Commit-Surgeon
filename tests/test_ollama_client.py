"""Unit tests for the Ollama HTTP client with mocked responses."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from config.settings import Settings
from ai_engine.exceptions import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from ai_engine.ollama_client import OllamaClient


@pytest.fixture
def test_settings():
    return Settings(
        ollama_api_url="http://localhost:11434",
        default_model="qwen3.5:4b",
        model_timeout=5,
    )


class TestOllamaClientStatus:
    """Test service and model availability checks."""

    def test_service_running_true(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.get", return_value=mock_resp):
            assert client.is_service_running() is True

    def test_service_running_false_on_connection_error(self, test_settings):
        client = OllamaClient(settings=test_settings)
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            assert client.is_service_running() is False

    def test_model_available_true(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "qwen3.5:4b"}]}
        with patch("requests.get", return_value=mock_resp):
            assert client.is_model_available("qwen3.5:4b") is True

    def test_model_available_false_when_missing(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"models": [{"name": "llama3:8b"}]}
        with patch("requests.get", return_value=mock_resp):
            assert client.is_model_available("qwen3.5:4b") is False


class TestOllamaClientChat:
    """Test chat inference endpoint handling."""

    def test_chat_success(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"role": "assistant", "content": '{"analysis_summary": "test"}'}
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            content, duration = client.chat([{"role": "user", "content": "hi"}])
            assert content == '{"analysis_summary": "test"}'
            assert duration >= 0.0

            # Verify request payload
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["model"] == "qwen3.5:4b"
            assert call_kwargs["json"]["format"] == "json"
            assert call_kwargs["timeout"] == 5

    def test_chat_timeout_raises(self, test_settings):
        client = OllamaClient(settings=test_settings)
        with patch("requests.post", side_effect=requests.exceptions.Timeout):
            with pytest.raises(OllamaTimeoutError, match="timed out"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_connection_failure_raises(self, test_settings):
        client = OllamaClient(settings=test_settings)
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError):
            with pytest.raises(OllamaConnectionError, match="Could not connect to Ollama"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_model_not_found_404(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "model not found"
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(OllamaModelNotFoundError, match="not found in Ollama"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_model_not_found_in_error_field(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "model 'qwen3.5:4b' not found"}
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(OllamaModelNotFoundError, match="not found"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_server_error_500(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "internal cuda error"}
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(OllamaResponseError, match="status 500"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_empty_content_raises(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "   "}}
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(OllamaResponseError, match="empty response content"):
                client.chat([{"role": "user", "content": "hi"}])

    def test_chat_malformed_envelope_raises(self, test_settings):
        client = OllamaClient(settings=test_settings)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"not_message": {}}
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(OllamaResponseError, match="Missing 'message' field"):
                client.chat([{"role": "user", "content": "hi"}])
