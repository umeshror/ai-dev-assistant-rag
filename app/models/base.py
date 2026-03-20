"""
app/models/base.py
──────────────────────────────────────────────────────────────────────────────
Shared/Base Pydantic models for the application.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Standardised error response body."""
    detail: str = Field(description="Human-readable error description")
    error_code: str = Field(description="Machine-readable error code")


class HealthResponse(BaseModel):
    """Response for the GET /health liveness probe."""
    status: Literal["ok"] = "ok"
    version: str = Field(description="Application version string")
