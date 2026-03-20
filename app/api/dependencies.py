"""
app/api/dependencies.py
──────────────────────────────────────────────────────────────────────────────
FastAPI dependency injection for the API layer.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from fastapi import Request

from app.services.analyzer import AnalyzerService


def get_analyzer_service(request: Request) -> AnalyzerService:
    """
    Dependency to provide a configured AnalyzerService instance.
    Uses RAGEngine and LLMClient from the application state (lifespan).
    """
    return AnalyzerService(
        settings=request.app.state.settings,
        rag_engine=request.app.state.rag_engine,
        llm_client=request.app.state.llm_client,
    )
