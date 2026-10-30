"""Exception hierarchy for AI engine and Ollama operations."""


class AIEngineError(Exception):
    """Base exception for all AI engine errors."""


# --- Ollama Client Errors ---


class OllamaClientError(AIEngineError):
    """Base exception for Ollama API communication errors."""


class OllamaConnectionError(OllamaClientError):
    """Raised when connection to Ollama daemon fails."""


class OllamaModelNotFoundError(OllamaClientError):
    """Raised when the specified model is not available locally in Ollama."""


class OllamaTimeoutError(OllamaClientError):
    """Raised when an inference request to Ollama times out."""


class OllamaResponseError(OllamaClientError):
    """Raised when Ollama returns an error status or invalid/malformed response."""


# --- Context Preparation Errors ---


class ContextPreparationError(AIEngineError):
    """Base exception for errors during change context extraction for the LLM."""


class ContextExceededLimitError(ContextPreparationError):
    """Raised when the diff context exceeds the configured max_context_size limit."""


class SensitiveFileDetectedError(ContextPreparationError):
    """Raised when a sensitive file is detected that should not be sent to LLM."""


# --- AI Analysis & Grouping Errors ---


class AIAnalysisError(AIEngineError):
    """Raised when AI change analysis cannot be performed."""


class GroupingValidationError(AIEngineError):
    """Base exception for validation errors in proposed commit groups."""


class CoverageValidationError(GroupingValidationError):
    """Raised when input changes are missing or not fully covered by grouping."""


class DuplicateChangeError(GroupingValidationError):
    """Raised when a change appears in multiple commit groups."""


class UnknownChangeIdError(GroupingValidationError):
    """Raised when the LLM returns change identifiers not present in the input."""


class MissingChangeIdError(GroupingValidationError):
    """Raised when input changes are silently omitted from the grouping."""


class EmptyGroupError(GroupingValidationError):
    """Raised when a proposed commit group contains zero changes."""


class InvalidConfidenceError(GroupingValidationError):
    """Raised when a confidence score falls outside the valid 0.0 - 1.0 range."""


class SourceStateMismatchError(GroupingValidationError):
    """Raised when a change's source state does not match the input."""
