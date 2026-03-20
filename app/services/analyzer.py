"""
app/services/analyzer.py
──────────────────────────────────────────────────────────────────────────────
Orchestrates the retrieval-augmented generation (RAG) pipeline to analyze
developer code against security and compliance policies.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.core.config import Settings
from app.core.exceptions import IndexNotFoundError
from app.engines.base import LLMProtocol, RAGProtocol
from app.models.analysis import AnalysisResult, AnalyzeRequest, AnalyzeResponse
from app.prompts.analysis import build_analysis_prompt

logger = logging.getLogger(__name__)


class AnalyzerService:
    """
    Business logic layer for analyzing code snippets.
    Acts as the orchestrator between the RAG layer and the LLM layer.
    """

    def __init__(
        self,
        settings: Settings,
        rag_engine: Optional[RAGProtocol],
        llm_client: LLMProtocol,
    ):
        self._settings = settings
        self._rag_engine = rag_engine
        self._llm_client = llm_client

    async def analyze_code(
        self,
        request: AnalyzeRequest,
        request_id: str = "unknown",
    ) -> AnalyzeResponse:
        """
        End-to-end analysis pipeline with grounded retrieval.
        """
        if self._rag_engine is None:
            raise IndexNotFoundError(
                "Policy index is not loaded. Contact the administrator."
            )

        context = {"request_id": request_id, "type": request.type}
        logger.info("Starting code analysis. context=%s", context)

        # Step 1: Retrieve relevant policies (Top-K)
        # RAGEngine now returns List[dict[str, Any]] with 'text' and 'score'
        retrieved_data = await self._rag_engine.retrieve(
            query=request.code,
            top_k=self._settings.top_k,
        )

        # Extract text chunks for the prompt builder
        retrieved_texts = [item["text"] for item in retrieved_data]

        if not retrieved_texts:
            logger.warning("No relevant policies found above threshold for request_id=%s", request_id)

        logger.info(
            "Retrieved %d policies for context. request_id=%s",
            len(retrieved_texts), request_id
        )

        # Step 2: Build prompt with grounded context
        messages = build_analysis_prompt(
            retrieved_policies=retrieved_texts,
            code_snippet=request.code,
            code_type=request.type,
        )

        # Step 3: Call LLM (Grounded execution)
        raw_analysis: dict[str, Any] = await self._llm_client.analyze(messages)

        logger.info("LLM analysis complete. request_id=%s", request_id)

        # Step 4: Map to response models
        analysis_result = AnalysisResult(
            violations=raw_analysis.get("violations", []),
            security_risks=raw_analysis.get("security_risks", []),
            suggestions=raw_analysis.get("suggestions", []),
        )

        return AnalyzeResponse(analysis=analysis_result)
