"""High-level coordinator for AI-powered Git change grouping."""

from typing import Optional

from config.settings import Settings, get_settings
from git_engine.models import RepositoryChanges
from ai_engine.analyzer import AIChangeAnalyzer
from ai_engine.context import prepare_change_context
from ai_engine.models import GroupingResult
from ai_engine.ollama_client import OllamaClient
from ai_engine.validator import GroupValidator


class ChangeGrouper:
    """Coordinator that prepares Git change context, executes LLM grouping, and validates output."""

    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        analyzer: Optional[AIChangeAnalyzer] = None,
        validator: Optional[GroupValidator] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.client = client or OllamaClient(settings=self.settings)
        self.validator = validator or GroupValidator()
        self.analyzer = analyzer or AIChangeAnalyzer(
            client=self.client,
            validator=self.validator,
            settings=self.settings,
        )

    def group_changes(self, changes: RepositoryChanges) -> GroupingResult:
        """Group repository changes into logical proposed commit groups.

        Args:
            changes: Structured RepositoryChanges output from git_engine.

        Returns:
            GroupingResult containing validated proposed commit groups.
        """
        # Step 1: Prepare and sanitize context
        context = prepare_change_context(changes, settings=self.settings)

        # Step 2: Handle sensitive files warnings
        warnings = []
        if context.excluded_files:
            warnings.append(
                f"Sensitive files excluded from LLM analysis for security: {', '.join(context.excluded_files)}"
            )

        # Step 3: Run AI analysis and grouping
        result = self.analyzer.analyze_and_group(context)

        if warnings:
            result.warnings.extend(warnings)

        return result


def group_repository_changes(
    changes: RepositoryChanges,
    client: Optional[OllamaClient] = None,
    settings: Optional[Settings] = None,
) -> GroupingResult:
    """Convenience functional interface for grouping repository changes."""
    grouper = ChangeGrouper(client=client, settings=settings)
    return grouper.group_changes(changes)
