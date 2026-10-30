"""Environment verification utilities for Commit Surgeon."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
import requests
from pydantic import BaseModel, Field

from config.settings import Settings, get_settings


class ComponentStatus(BaseModel):
    """Status for an individual system component."""

    name: str
    label: str  # e.g., "Installed", "Missing", "Running", "Not Running", "Available", "Not Available"
    is_ok: bool
    details: str = ""
    instructions: Optional[str] = None


class EnvironmentReport(BaseModel):
    """Consolidated environment check report."""

    python: ComponentStatus
    git: ComponentStatus
    ollama: ComponentStatus
    model: ComponentStatus
    all_ready: bool = False
    endpoint_warning: Optional[str] = Field(default=None, description="Warning if Ollama endpoint is non-loopback")


def check_python() -> ComponentStatus:
    """Check Python installation and version."""
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        return ComponentStatus(
            name="Python",
            label="Installed",
            is_ok=True,
            details=f"Python {version} ({sys.executable})",
        )
    return ComponentStatus(
        name="Python",
        label="Missing",
        is_ok=False,
        details=f"Python {version} is below recommended 3.10+",
        instructions="Please install Python 3.10 or higher.",
    )


def check_git(repo_dir: Optional[str] = None) -> ComponentStatus:
    """Check Git executable availability, version, and repository status (strictly non-destructive)."""
    git_exec = shutil.which("git")
    if not git_exec:
        return ComponentStatus(
            name="Git",
            label="Missing",
            is_ok=False,
            details="Git executable not found in PATH",
            instructions="Please install Git from https://git-scm.com/ and add it to PATH.",
        )

    try:
        ver_proc = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        git_version = ver_proc.stdout.strip() if ver_proc.returncode == 0 else "Unknown version"
    except Exception as exc:
        return ComponentStatus(
            name="Git",
            label="Missing",
            is_ok=False,
            details=f"Failed to execute git: {exc}",
            instructions="Please verify Git installation.",
        )

    # Check if target directory is a git repository (read-only check)
    target = Path(repo_dir) if repo_dir else Path.cwd()
    try:
        repo_proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(target),
            capture_output=True,
            text=True,
            check=False,
        )
        is_repo = repo_proc.returncode == 0 and "true" in repo_proc.stdout.lower()
    except Exception:
        is_repo = False

    repo_msg = "Git repository detected" if is_repo else "Not a Git repository"
    return ComponentStatus(
        name="Git",
        label="Installed",
        is_ok=True,
        details=f"{git_version} ({repo_msg})",
    )


def check_ollama_service(api_url: str, timeout: int = 3) -> ComponentStatus:
    """Check if Ollama local service is running and accessible."""
    try:
        response = requests.get(f"{api_url.rstrip('/')}/api/tags", timeout=timeout)
        if response.status_code == 200:
            return ComponentStatus(
                name="Ollama",
                label="Running",
                is_ok=True,
                details=f"Service reachable at {api_url}",
            )
        return ComponentStatus(
            name="Ollama",
            label="Not Running",
            is_ok=False,
            details=f"Service returned HTTP {response.status_code}",
            instructions="Ensure the Ollama daemon is running with 'ollama serve'.",
        )
    except Exception:
        ollama_bin = shutil.which("ollama")
        install_info = "Ollama binary is installed" if ollama_bin else "Ollama binary is not installed"
        return ComponentStatus(
            name="Ollama",
            label="Not Running",
            is_ok=False,
            details=f"Cannot connect to {api_url} ({install_info})",
            instructions=(
                "Ollama is not running. Please start Ollama using:\n"
                "  ollama serve\n"
                "Or launch the Ollama desktop application."
            ),
        )


def check_local_model(
    api_url: str, model_name: str, ollama_running: bool, timeout: int = 3
) -> ComponentStatus:
    """Check if the required local model is available in Ollama."""
    if not ollama_running:
        return ComponentStatus(
            name="Local Model",
            label="Unknown",
            is_ok=False,
            details=f"Cannot check model '{model_name}': Ollama is not running",
            instructions=(
                f"Once Ollama is running, pull the model using:\n"
                f"  ollama pull {model_name}\n"
                f"Note: '{model_name}' is a 4-billion (4B) parameter open-source model suitable for offline inference."
            ),
        )

    try:
        response = requests.get(f"{api_url.rstrip('/')}/api/tags", timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            target_base = model_name.split(":")[0].lower()
            target_full = model_name.lower()

            model_names = [m.get("name", "").lower() for m in models]
            found = any(
                target_full == name or name.startswith(target_full) or target_base in name
                for name in model_names
            )

            if found:
                return ComponentStatus(
                    name="Local Model",
                    label="Available",
                    is_ok=True,
                    details=f"Model '{model_name}' is available locally",
                )

            return ComponentStatus(
                name="Local Model",
                label="Not Available",
                is_ok=False,
                details=f"Model '{model_name}' is not found in local Ollama library",
                instructions=(
                    f"To install the intended model, run:\n"
                    f"  ollama pull {model_name}\n\n"
                    f"About this model: '{model_name}' is an open-source model with approximately "
                    f"4 billion parameters (4B), designed to run efficiently on local hardware "
                    f"without sending code or diffs to cloud services."
                ),
            )
    except Exception as exc:
        return ComponentStatus(
            name="Local Model",
            label="Unknown",
            is_ok=False,
            details=f"Error querying models from Ollama: {exc}",
            instructions=f"Run 'ollama pull {model_name}' once Ollama is operational.",
        )

    return ComponentStatus(
        name="Local Model",
        label="Unknown",
        is_ok=False,
        details="Could not verify model status",
    )


def is_loopback_url(url: str) -> bool:
    """Check if a URL points to a loopback/localhost address.
    
    Returns True for localhost, 127.0.0.1, ::1, and [::1].
    Returns False for all other addresses.
    """
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        hostname = hostname.lower().strip("[]")
        return hostname in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


def run_environment_check(
    settings: Optional[Settings] = None,
    repo_dir: Optional[str] = None,
) -> EnvironmentReport:
    """Run complete environment verification."""
    cfg = settings or get_settings()

    python_status = check_python()
    git_status = check_git(repo_dir=repo_dir)
    ollama_status = check_ollama_service(api_url=cfg.ollama_api_url)
    model_status = check_local_model(
        api_url=cfg.ollama_api_url,
        model_name=cfg.default_model,
        ollama_running=ollama_status.is_ok,
    )

    # Warn if Ollama endpoint is non-loopback (security concern for offline-first tool)
    endpoint_warning = None
    if not is_loopback_url(cfg.ollama_api_url):
        endpoint_warning = (
            f"WARNING: OLLAMA_API_URL is set to a non-loopback address ({cfg.ollama_api_url}). "
            f"Code and diffs may be transmitted over the network. "
            f"For offline-first security, use http://localhost:11434 or http://127.0.0.1:11434."
        )

    all_ready = (
        python_status.is_ok
        and git_status.is_ok
        and ollama_status.is_ok
        and model_status.is_ok
    )

    return EnvironmentReport(
        python=python_status,
        git=git_status,
        ollama=ollama_status,
        model=model_status,
        all_ready=all_ready,
        endpoint_warning=endpoint_warning,
    )
