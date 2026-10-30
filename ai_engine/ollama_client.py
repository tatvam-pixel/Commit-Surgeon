"""Ollama HTTP client for local LLM inference."""

import json
import time
from typing import Any, Dict, List, Optional, Tuple
import requests

from config.settings import Settings, get_settings
from ai_engine.exceptions import (
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)


class OllamaClient:
    """Client for communicating with the local Ollama REST API."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.ollama_api_url.rstrip("/")
        self.default_model = self.settings.default_model
        self.timeout = self.settings.model_timeout
        self.temperature = getattr(self.settings, "ai_temperature", 0.1)

    def is_service_running(self) -> bool:
        """Check if the Ollama service daemon is reachable."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def is_model_available(self, model_name: Optional[str] = None) -> bool:
        """Check if the requested model exists in local Ollama catalog."""
        target = (model_name or self.default_model).lower()
        target_base = target.split(":")[0]
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = data.get("models", [])
            for m in models:
                name = m.get("name", "").lower()
                if name == target or name.startswith(f"{target_base}:") or name == target_base:
                    return True
            return False
        except Exception:
            return False

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        format_json: bool = True,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[str, float]:
        """Send chat messages to Ollama /api/chat and return (content, duration_seconds).

        Raises:
            OllamaConnectionError: If daemon is unreachable.
            OllamaTimeoutError: If inference exceeds timeout limit.
            OllamaModelNotFoundError: If requested model is missing.
            OllamaResponseError: If server responds with error or malformed payload.
        """
        model_to_use = model or self.default_model
        temp = temperature if temperature is not None else self.temperature
        req_timeout = timeout if timeout is not None else self.timeout

        payload: Dict[str, Any] = {
            "model": model_to_use,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temp,
            },
        }
        if format_json:
            payload["format"] = "json"

        url = f"{self.base_url}/api/chat"
        start_time = time.perf_counter()

        try:
            resp = requests.post(url, json=payload, timeout=req_timeout)
        except requests.exceptions.Timeout as exc:
            raise OllamaTimeoutError(
                f"Inference request for model '{model_to_use}' timed out after {req_timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise OllamaConnectionError(
                f"Could not connect to Ollama service at {self.base_url}. Ensure 'ollama serve' is running."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise OllamaConnectionError(
                f"Network request to Ollama failed: {exc}"
            ) from exc

        elapsed = time.perf_counter() - start_time

        # Handle HTTP error status codes
        if resp.status_code == 404:
            raise OllamaModelNotFoundError(
                f"Model '{model_to_use}' not found in Ollama. Pull it using: ollama pull {model_to_use}"
            )

        if resp.status_code >= 400:
            try:
                err_data = resp.json()
                err_msg = err_data.get("error", resp.text)
            except Exception:
                err_msg = resp.text
            if "not found" in err_msg.lower():
                raise OllamaModelNotFoundError(
                    f"Model '{model_to_use}' not found: {err_msg}. Pull with: ollama pull {model_to_use}"
                )
            raise OllamaResponseError(
                f"Ollama server returned error status {resp.status_code}: {err_msg}"
            )

        # Parse JSON response envelope
        try:
            data = resp.json()
        except Exception as exc:
            raise OllamaResponseError(
                f"Ollama returned malformed non-JSON response envelope: {resp.text[:200]}"
            ) from exc

        if not isinstance(data, dict):
            raise OllamaResponseError(f"Unexpected response structure from Ollama: {type(data)}")

        if "error" in data:
            err_msg = data["error"]
            if "not found" in err_msg.lower():
                raise OllamaModelNotFoundError(
                    f"Model '{model_to_use}' not found: {err_msg}. Pull with: ollama pull {model_to_use}"
                )
            raise OllamaResponseError(f"Ollama reported error: {err_msg}")

        message_obj = data.get("message")
        if not message_obj or not isinstance(message_obj, dict):
            raise OllamaResponseError("Missing 'message' field in Ollama chat response")

        content = message_obj.get("content", "")
        if not content or not content.strip():
            raise OllamaResponseError("Ollama returned an empty response content")

        return content, elapsed
