"""
app/config.py
──────────────────────────────────────────────────────────────────────────────
Centralised, environment-driven configuration using pydantic-settings.
All configuration is injected via environment variables (or .env file).
No values are hard-coded in this module.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Precedence (highest → lowest):
      1. Actual environment variables
      2. .env file
      3. Field default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI ────────────────────────────────────────────────────────────
    openai_api_key: str = Field(..., description="OpenAI API key (required)")

    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model name",
    )

    chat_model: str = Field(
        default="gpt-4o",
        description="OpenAI chat completion model name",
    )

    # ── RAG / Retrieval ────────────────────────────────────────────────────
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of policy chunks to retrieve from FAISS",
    )

    faiss_index_path: str = Field(
        default="./data/faiss_index",
        description="Directory path for persisted FAISS index files",
    )

    policies_file_path: str = Field(
        default="./data/policies.txt",
        description="Path to the raw policies text file",
    )

    # ── LLM Generation ────────────────────────────────────────────────────
    llm_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for LLM (low = more deterministic)",
    )

    llm_max_tokens: int = Field(
        default=1024,
        ge=128,
        le=4096,
        description="Maximum tokens in the LLM response",
    )

    llm_timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="HTTP timeout for LLM API calls (seconds)",
    )

    llm_max_retries: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum number of retry attempts for LLM calls",
    )

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Root logging level",
    )

    # ── App ───────────────────────────────────────────────────────────────
    app_name: str = Field(
        default="AI Developer Assistant",
        description="Human-readable application name",
    )

    app_version: str = Field(
        default="1.0.0",
        description="Application version string",
    )

    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment",
    )

    @field_validator("openai_api_key")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("OPENAI_API_KEY must not be empty")
        return v.strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached singleton Settings instance.

    Using lru_cache ensures the .env file is parsed exactly once per process,
    avoiding repeated I/O on every request.
    """
    return Settings()
