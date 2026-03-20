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
from app.engines.llm import LLMClient
from app.engines.rag import RAGEngine
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
        rag_engine: Optional[RAGEngine],
        llm_client: LLMClient,
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
        End-to-end analysis pipeline.

        1. Retrieve relevant policies from FAISS via RAGEngine.
        2. Format grounded prompt using prompts/analysis.py.
        3. Call LLM via LLMClient.
        4. Package and return structured response.
        """
        if self._rag_engine is None:
            raise IndexNotFoundError(
                "Policy index is not loaded. Contact the administrator."
            )

        logger.info(
            "request_id=%s Analyzing %s snippet (length=%d chars)",
            request_id,
            request.type,
            len(request.code),
        )

        # Step 1: Retrieve relevant policies (Top-K)
        retrieved_policies = await self._rag_engine.retrieve(
            query=request.code,
            top_k=self._settings.top_k,
        )

        logger.info(
            "request_id=%s Retrieved %d policies for context",
            request_id,
            len(retrieved_policies),
        )

        # Step 2: Build prompt with grounded context
        messages = build_analysis_prompt(
            retrieved_policies=retrieved_policies,
            code_snippet=request.code,
            code_type=request.type,
        )

        # Step 3: Call LLM (Grounded execution)
        raw_analysis: dict[str, Any] = await self._llm_client.analyze(messages)

        logger.info("request_id=%s LLM analysis response received.", request_id)

        # Step 4: Parse and map to response models
        analysis_result = AnalysisResult(
            violations=raw_analysis.get("violations", []),
            security_risks=raw_analysis.get("security_risks", []),
            suggestions=raw_analysis.get("suggestions", []),
        )

        return AnalyzeResponse(analysis=analysis_result)
