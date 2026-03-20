"""
app/core/exceptions.py
──────────────────────────────────────────────────────────────────────────────
Global application exceptions. Mapping these to HTTP status codes is handled
in the API layer.
──────────────────────────────────────────────────────────────────────────────
"""

class BaseAppError(Exception):
    """Base exception for all application-specific errors."""
    def __init__(self, message: str, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class LLMError(BaseAppError):
    """Raised when the LLM provider fails or returns an invalid response."""
    def __init__(self, message: str):
        super().__init__(message, error_code="LLM_ERROR")

class IndexNotFoundError(BaseAppError):
    """Raised when the FAISS index files are not found on disk."""
    def __init__(self, message: str):
        super().__init__(message, error_code="INDEX_NOT_FOUND")

class EmbeddingError(BaseAppError):
    """Raised when the embedding API fails during query processing."""
    def __init__(self, message: str):
        super().__init__(message, error_code="EMBEDDING_ERROR")

class EmptyQueryError(BaseAppError):
    """Raised when the user submits an empty or whitespace-only code snippet."""
    def __init__(self, message: str):
        super().__init__(message, error_code="EMPTY_QUERY")
