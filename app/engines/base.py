"""
app/engines/base.py
──────────────────────────────────────────────────────────────────────────────
Base protocols for engine abstractions.
Enables dependency inversion and easier mocking for tests.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Any, List, Protocol, runtime_checkable

from app.models.analysis import AnalysisResult


@runtime_checkable
class RAGProtocol(Protocol):
    """Protocol for a Retrieval-Augmented Generation engine."""

    async def retrieve(self, query: str, top_k: int) -> List[dict[str, Any]]:
        """
        Retrieve relevant context for a given query.
        Returns a list of dictionaries containing 'text', 'score', and optional 'metadata'.
        """
        ...

    def load_index(self) -> None:
        """Load the vector index into memory."""
        ...


@runtime_checkable
class LLMProtocol(Protocol):
    """Protocol for a Language Model client."""

    async def analyze(self, messages: List[dict[str, str]]) -> dict[str, Any]:
        """
        Generate an analysis based on the provided messages (grounded prompt).
        Returns a dictionary mapping to the AnalysisResult schema.
        """
        ...
