"""
app/api/routes.py
──────────────────────────────────────────────────────────────────────────────
FastAPI route definitions for the application.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies import get_analyzer_service
from app.models.analysis import AnalyzeRequest, AnalyzeResponse, HealthResponse
from app.services.analyzer import AnalyzerService

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["Operations"],
    summary="Liveness probe",
)
async def health_check(request: Request) -> HealthResponse:
    """Liveness probe. Returns 200 when the service is running."""
    return HealthResponse(version=request.app.state.settings.app_version)


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    tags=["Analysis"],
    summary="Analyze code against security policies",
    status_code=status.HTTP_200_OK,
)
async def analyze(
    request: Request,
    body: AnalyzeRequest,
    analyzer: AnalyzerService = Depends(get_analyzer_service),
) -> AnalyzeResponse:
    """
    Analyze developer code or infrastructure against internal policies.
    Orchestrated by the AnalyzerService.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    return await analyzer.analyze_code(body, request_id=request_id)
