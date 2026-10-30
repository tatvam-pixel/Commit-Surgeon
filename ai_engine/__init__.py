"""AI engine package for Commit Surgeon: local LLM inference and semantic change grouping."""

from ai_engine.analyzer import AIChangeAnalyzer
from ai_engine.context import is_sensitive_file, prepare_change_context
from ai_engine.exceptions import (
    AIEngineError,
    AIAnalysisError,
    ContextExceededLimitError,
    ContextPreparationError,
    CoverageValidationError,
    DuplicateChangeError,
    EmptyGroupError,
    GroupingValidationError,
    InvalidConfidenceError,
    MissingChangeIdError,
    OllamaClientError,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
    SensitiveFileDetectedError,
    SourceStateMismatchError,
    UnknownChangeIdError,
)
from ai_engine.grouper import ChangeGrouper, group_repository_changes
from ai_engine.models import (
    ChangeAnalysis,
    ChangeContextItem,
    GroupingResult,
    PreparedChangeContext,
    ProposedCommitGroup,
)
from ai_engine.ollama_client import OllamaClient
from ai_engine.validator import GroupValidator

__all__ = [
    # Clients & Coordinators
    "OllamaClient",
    "AIChangeAnalyzer",
    "ChangeGrouper",
    "group_repository_changes",
    "GroupValidator",
    "prepare_change_context",
    "is_sensitive_file",
    # Data Models
    "ChangeAnalysis",
    "ProposedCommitGroup",
    "GroupingResult",
    "ChangeContextItem",
    "PreparedChangeContext",
    # Exceptions
    "AIEngineError",
    "OllamaClientError",
    "OllamaConnectionError",
    "OllamaModelNotFoundError",
    "OllamaTimeoutError",
    "OllamaResponseError",
    "ContextPreparationError",
    "ContextExceededLimitError",
    "SensitiveFileDetectedError",
    "AIAnalysisError",
    "GroupingValidationError",
    "CoverageValidationError",
    "DuplicateChangeError",
    "UnknownChangeIdError",
    "MissingChangeIdError",
    "EmptyGroupError",
    "InvalidConfidenceError",
    "SourceStateMismatchError",
]
