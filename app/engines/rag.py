"""
app/engines/rag.py
──────────────────────────────────────────────────────────────────────────────
Retrieval-Augmented Generation (RAG) engine.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import faiss
import numpy as np
import numpy.typing as npt
from openai import APIError, AsyncOpenAI

from app.core.config import Settings
from app.core.exceptions import EmbeddingError, EmptyQueryError, IndexNotFoundError

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Manages FAISS-based policy retrieval using OpenAI embeddings.
    """

    _INDEX_FILE = "index.faiss"
    _CHUNKS_FILE = "chunks.npy"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._index: Optional[faiss.Index] = None
        self._policy_chunks: List[str] = []

    def load_index(self) -> None:
        """Load the FAISS index and policy chunks from disk."""
        index_dir = Path(self._settings.faiss_index_path)
        index_path = index_dir / self._INDEX_FILE
        chunks_path = index_dir / self._CHUNKS_FILE

        if not index_path.exists():
            raise IndexNotFoundError(f"FAISS index not found at '{index_path}'")

        if not chunks_path.exists():
            raise IndexNotFoundError(f"Policy chunks file not found at '{chunks_path}'")

        logger.info("Loading FAISS index from '%s'", index_path)
        self._index = faiss.read_index(str(index_path))
        self._policy_chunks = np.load(str(chunks_path), allow_pickle=True).tolist()

        logger.info(
            "FAISS index loaded. Vectors: %d | Policy chunks: %d",
            self._index.ntotal,
            len(self._policy_chunks),
        )

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[dict[str, Any]]:
        """
        Retrieve relevant policy chunks based on semantic similarity.
        Filters by similarity_threshold (L2 distance).
        """
        if not query or not query.strip():
            raise EmptyQueryError("Query text cannot be empty.")

        if self._index is None:
            raise IndexNotFoundError("FAISS index is not available.")

        k = top_k if top_k is not None else self._settings.top_k
        k = min(k, self._index.ntotal)

        if k <= 0:
            return []

        # Convert query to embedding
        query_vector = await self._embed_query(query)

        # Search FAISS index
        distances, indices = self._index.search(query_vector, k)

        results: List[dict[str, Any]] = []
        threshold = self._settings.similarity_threshold

        for dist, idx in zip(distances[0], indices[0]):
            # FAISS IndexFlatL2 returns squared L2 distance.
            # Lower is more similar.
            if dist > threshold:
                logger.debug("Skipping policy chunk with distance %.3f > %.3f", dist, threshold)
                continue

            if 0 <= idx < len(self._policy_chunks):
                results.append({
                    "text": self._policy_chunks[idx],
                    "score": float(dist),
                    "metadata": {"index": int(idx)}
                })

        logger.info(
            "Retrieved %d policies (threshold=%.2f, limit=%d)",
            len(results), threshold, k
        )
        return results

    async def _embed_query(self, text: str) -> npt.NDArray[np.float32]:
        """Embed a single text string."""
        try:
            response = await self._client.embeddings.create(
                model=self._settings.embedding_model,
                input=text,
            )
            return np.array(
                response.data[0].embedding, dtype=np.float32
            ).reshape(1, -1)
        except APIError as exc:
            raise EmbeddingError(f"OpenAI embedding error: {exc}") from exc
        except Exception as exc:
            raise EmbeddingError(f"Unexpected embedding error: {exc}") from exc

    async def embed_texts(self, texts: List[str]) -> npt.NDArray[np.float32]:
        """Embed multiple texts in a single call (used by ingest.py)."""
        if not texts:
            raise ValueError("texts must not be empty")

        try:
            response = await self._client.embeddings.create(
                model=self._settings.embedding_model,
                input=texts,
            )
            return np.array(
                [item.embedding for item in response.data], dtype=np.float32
            )
        except APIError as exc:
            raise EmbeddingError(f"Batch embedding failed: {exc}") from exc
