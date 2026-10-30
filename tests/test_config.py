"""Tests for configuration management."""

import os
from unittest.mock import patch
import pytest

from config.settings import Settings, get_settings


def test_default_settings_values():
    """Verify that default settings match project requirements."""
    settings = Settings()
    assert settings.app_name == "Commit Surgeon"
    assert settings.app_version == "0.1.0"
    assert settings.ollama_api_url == "http://localhost:11434"
    assert settings.default_model == "qwen3.5:4b"
    assert settings.model_timeout == 60
    assert settings.max_diff_size == 100000
    assert settings.debug is False


def test_custom_settings_instantiation():
    """Verify that settings can be customized during instantiation."""
    custom = Settings(
        app_name="Custom Surgeon",
        app_version="0.2.0",
        ollama_api_url="http://custom-host:11434",
        default_model="llama3.2:3b",
        model_timeout=30,
        max_diff_size=50000,
        debug=True,
    )
    assert custom.app_name == "Custom Surgeon"
    assert custom.app_version == "0.2.0"
    assert custom.ollama_api_url == "http://custom-host:11434"
    assert custom.default_model == "llama3.2:3b"
    assert custom.model_timeout == 30
    assert custom.max_diff_size == 50000
    assert custom.debug is True


def test_settings_load_from_environment(monkeypatch):
    """Verify settings read from environment variables."""
    monkeypatch.setenv("APP_NAME", "Env Surgeon")
    monkeypatch.setenv("APP_VERSION", "1.0.0")
    monkeypatch.setenv("OLLAMA_API_URL", "http://ollama-server:11434")
    monkeypatch.setenv("DEFAULT_MODEL", "qwen3.5:4b")
    monkeypatch.setenv("MODEL_TIMEOUT", "120")
    monkeypatch.setenv("MAX_DIFF_SIZE", "200000")
    monkeypatch.setenv("DEBUG", "true")

    settings = get_settings()
    assert settings.app_name == "Env Surgeon"
    assert settings.app_version == "1.0.0"
    assert settings.ollama_api_url == "http://ollama-server:11434"
    assert settings.default_model == "qwen3.5:4b"
    assert settings.model_timeout == 120
    assert settings.max_diff_size == 200000
    assert settings.debug is True
