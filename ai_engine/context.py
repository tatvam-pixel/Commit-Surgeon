"""Preparation and sanitization of Git changes context for LLM ingestion."""

import re
from pathlib import Path
from typing import List, Optional, Set
from pydantic import BaseModel

from config.settings import Settings, get_settings
from git_engine.models import DiffHunk, FileChange, RepositoryChanges
from ai_engine.exceptions import ContextExceededLimitError, ContextPreparationError, SensitiveFileDetectedError
from ai_engine.models import ChangeContextItem, PreparedChangeContext

# Patterns identifying files that must never be sent to the LLM
SENSITIVE_FILENAME_PATTERNS = [
    re.compile(r"^\.env(\..+)?$", re.IGNORECASE),
    re.compile(r"^.*\.env$", re.IGNORECASE),
    re.compile(r"^id_(rsa|dsa|ecdsa|ed25519)(.*)?$", re.IGNORECASE),
    re.compile(r"^.*(credentials|client_secret|service[-_]?account|private[-_]?key).*\.(json|ya?ml|xml)$", re.IGNORECASE),
    re.compile(r"^wp-config\.php$", re.IGNORECASE),
    re.compile(r"^secrets?\.(ya?ml|json|toml)$", re.IGNORECASE),
]

SENSITIVE_EXTENSIONS = {
    ".pem",
    ".key",
    ".pkcs12",
    ".p12",
    ".pfx",
    ".crt",
    ".der",
    ".kdbx",
}


def is_sensitive_file(file_path: str) -> bool:
    """Determine whether a file is considered sensitive or credential-bearing."""
    p = Path(file_path.replace("\\", "/"))
    name = p.name.lower()

    # Check extension
    if p.suffix.lower() in SENSITIVE_EXTENSIONS:
        return True

    # Check filename patterns
    for pat in SENSITIVE_FILENAME_PATTERNS:
        if pat.match(name):
            return True

    # Check password or secret in name
    if "password" in name or "secret" in name:
        return True

    return False


def prepare_change_context(
    changes: RepositoryChanges,
    settings: Optional[Settings] = None,
    enforce_sensitive_check: bool = True,
) -> PreparedChangeContext:
    """Convert RepositoryChanges into a compact, sanitized context for LLM analysis.

    Raises:
        ContextExceededLimitError: If total context exceeds max_context_size or input was truncated.
    """
    cfg = settings or get_settings()
    max_context = getattr(cfg, "max_context_size", 50000)

    # Block AI analysis when merge conflicts exist
    if changes.has_conflicts:
        conflicted_files = [
            c.file_path for c in changes.changes if c.change_type == "conflicted"
        ]
        raise ContextPreparationError(
            f"Cannot perform AI analysis: repository has unresolved merge conflicts "
            f"in {len(conflicted_files)} file(s): {', '.join(conflicted_files) if conflicted_files else 'unknown files'}. "
            f"Resolve conflicts before running AI grouping."
        )

    # Check if Git engine previously encountered truncation
    if changes.has_truncated_content:
        raise ContextExceededLimitError(
            "Cannot perform safe AI analysis: Git diff extraction was truncated due to repository size limits."
        )

    context_items: List[ChangeContextItem] = []
    excluded_files: List[str] = []
    total_chars = 0

    repo_name = Path(changes.repository.root_path).name if changes.repository.root_path else "unknown"
    branch_name = changes.repository.current_branch

    for fc in changes.changes:
        norm_path = fc.file_path.replace("\\", "/")

        # 1. Filter sensitive files
        if enforce_sensitive_check and is_sensitive_file(norm_path):
            excluded_files.append(norm_path)
            continue

        # 2. Handle binary files
        if fc.is_binary:
            change_id = f"binary_{norm_path.replace('/', '_')}"
            diff_text = f"Binary file {norm_path} differs (binary content withheld)"
            item = ChangeContextItem(
                change_id=change_id,
                file_path=norm_path,
                source_state="untracked" if fc.is_untracked else ("staged" if fc.is_staged else "unstaged"),
                change_type=fc.change_type,
                added_lines=0,
                deleted_lines=0,
                header="Binary file",
                diff_content=diff_text,
            )
            total_chars += len(diff_text)
            context_items.append(item)
            continue

        # 3. Handle files with hunks
        if fc.hunks:
            for hunk in fc.hunks:
                # Sanitize hunk content: enforce string length
                hunk_content = hunk.content
                item = ChangeContextItem(
                    change_id=hunk.hunk_id,
                    file_path=norm_path,
                    source_state=hunk.source_state,
                    change_type=fc.change_type,
                    added_lines=hunk.added_lines,
                    deleted_lines=hunk.deleted_lines,
                    header=hunk.header,
                    diff_content=hunk_content,
                )
                total_chars += len(hunk_content) + len(hunk.hunk_id) + len(norm_path)
                context_items.append(item)
        else:
            # File with no hunks (e.g. empty added file or untracked empty file)
            change_id = f"file_{norm_path.replace('/', '_')}"
            summary_content = f"File {norm_path} marked as {fc.change_type} with 0 lines changed"
            item = ChangeContextItem(
                change_id=change_id,
                file_path=norm_path,
                source_state="staged" if fc.is_staged else ("untracked" if fc.is_untracked else "unstaged"),
                change_type=fc.change_type,
                added_lines=fc.added_lines,
                deleted_lines=fc.deleted_lines,
                header="",
                diff_content=summary_content,
            )
            total_chars += len(summary_content)
            context_items.append(item)

    # Validate against context limit
    if total_chars > max_context:
        raise ContextExceededLimitError(
            f"Prepared diff context ({total_chars} chars) exceeds maximum allowed limit ({max_context} chars). "
            "Analysis cannot be completed safely without risking model truncation."
        )

    return PreparedChangeContext(
        items=context_items,
        total_chars=total_chars,
        excluded_files=excluded_files,
        is_truncated=False,
        repository_name=repo_name,
        repository_branch=branch_name,
    )
