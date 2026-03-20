"""
scripts/ingest.py
──────────────────────────────────────────────────────────────────────────────
One-time ingestion script: reads policies.txt, embeds every policy chunk
using the OpenAI Embeddings API, builds a FAISS index, and saves both the
index and the raw chunks to disk.

Usage:
    python scripts/ingest.py [--policies PATH] [--index-dir PATH]

Run this script once before starting the API server.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import List

import faiss
import numpy as np

# Make sure the project root is in the Python path when running the script
# directly (e.g., `python scripts/ingest.py` from the project root).
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.engines.rag import RAGEngine
from app.core.exceptions import EmbeddingError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── File names (must match RAGEngine constants) ────────────────────────────────
_INDEX_FILE = "index.faiss"
_CHUNKS_FILE = "chunks.npy"


def _load_policy_chunks(file_path: Path) -> List[str]:
    """
    Parse the policies text file into individual policy chunks.

    Rules:
      - Blank lines are ignored.
      - Lines starting with # are comments and are ignored.
      - Each non-empty, non-comment line becomes one chunk.
    """
    if not file_path.exists():
        logger.error("Policies file not found: %s", file_path)
        sys.exit(1)

    chunks: list[str] = []
    with file_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                chunks.append(line)

    logger.info("Loaded %d policy chunks from '%s'", len(chunks), file_path)
    return chunks


async def _embed_all(
    engine: RAGEngine, chunks: List[str], batch_size: int = 100
) -> np.ndarray:
    """
    Embed all policy chunks in batches to respect API rate limits.

    Returns:
        Concatenated (N, D) float32 numpy array.
    """
    all_vectors: List[np.ndarray] = []
    total = len(chunks)

    for start in range(0, total, batch_size):
        batch = chunks[start : start + batch_size]
        batch_end = min(start + batch_size, total)

        logger.info(
            "Embedding batch %d–%d / %d ...",
            start + 1,
            batch_end,
            total,
        )

        try:
            vectors = await engine.embed_texts(batch)
            all_vectors.append(vectors)
        except EmbeddingError as exc:
            logger.error("Embedding failed for batch %d–%d: %s", start + 1, batch_end, exc)
            sys.exit(1)

    return np.vstack(all_vectors).astype(np.float32)


def _build_and_save_index(
    vectors: np.ndarray,
    chunks: list[str],
    index_dir: Path,
) -> None:
    """
    Build a FAISS IndexFlatL2 from the embedding matrix and persist it.

    IndexFlatL2 performs exact nearest-neighbour search — suitable for
    a policy corpus of up to ~100k items. For larger corpora, consider
    IndexIVFFlat with a trained quantiser.
    """
    index_dir.mkdir(parents=True, exist_ok=True)

    dimension = vectors.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(vectors)

    index_path = index_dir / _INDEX_FILE
    chunks_path = index_dir / _CHUNKS_FILE

    faiss.write_index(index, str(index_path))
    logger.info("FAISS index saved to '%s' (vectors=%d, dim=%d)", index_path, index.ntotal, dimension)

    np.save(str(chunks_path), np.array(chunks, dtype=object), allow_pickle=True)
    logger.info("Policy chunks saved to '%s'", chunks_path)


async def _run(policies_path: Path, index_dir: Path) -> None:
    """Main async ingestion pipeline."""
    settings = get_settings()

    logger.info("=== AI Developer Assistant — Policy Ingestion ===")
    logger.info("Embedding model : %s", settings.embedding_model)
    logger.info("Policies file   : %s", policies_path)
    logger.info("Index directory : %s", index_dir)

    # Load raw policy text
    chunks = _load_policy_chunks(policies_path)
    if not chunks:
        logger.error("No policy chunks found. Aborting.")
        sys.exit(1)

    # Generate embeddings
    engine = RAGEngine(settings=settings)
    vectors = await _embed_all(engine, chunks)

    # Build and persist FAISS index
    _build_and_save_index(vectors, chunks, index_dir)

    logger.info(
        "✅  Ingestion complete. %d policies indexed and saved to '%s'.",
        len(chunks),
        index_dir,
    )


def main() -> None:
    settings = get_settings()

    parser = argparse.ArgumentParser(
        description="Build the FAISS policy index for the AI Developer Assistant."
    )
    parser.add_argument(
        "--policies",
        type=Path,
        default=Path(settings.policies_file_path),
        help="Path to the policies text file (default: from config)",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path(settings.faiss_index_path),
        help="Directory to save the FAISS index (default: from config)",
    )
    args = parser.parse_args()

    asyncio.run(_run(args.policies, args.index_dir))


if __name__ == "__main__":
    main()
