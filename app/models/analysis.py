"""
app/models/analysis.py
──────────────────────────────────────────────────────────────────────────────
Analysis-specific Pydantic models.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

# Re-export base models for convenience if needed, or import directly in routes
from app.models.base import ErrorDetail, HealthResponse


class AnalyzeRequest(BaseModel):
    """Payload for code analysis."""
    code: str = Field(
        min_length=1,
        max_length=32_000,
        description="Raw code or configuration to analyze",
    )
    type: Literal["terraform", "yaml", "code"] = Field(
        description="Type of artifact being analyzed"
    )

    @field_validator("code")
    @classmethod
    def code_must_not_be_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("'code' must not be blank")
        return v


class AnalysisResult(BaseModel):
    """Structured output from LLM analysis."""
    violations: List[str] = Field(default_factory=list)
    security_risks: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """Top-level response envelope."""
    analysis: AnalysisResult
