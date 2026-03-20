# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — AI Developer Assistant (RAG-based)
# ─────────────────────────────────────────────────────────────────────────────
#
# Build strategy:
#   Stage 1 (builder): Install Python dependencies into a virtual environment.
#   Stage 2 (runtime): Copy only the venv and app code. No build tools in prod.
#
# Security:
#   - Base image: python:3.11-slim (minimal attack surface)
#   - Non-root user: appuser (UID 1001)
#   - No secrets baked into the image (all via environment variables)
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for faiss-cpu and numpy
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip --no-cache-dir \
    && pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Security: create non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copy Python virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/policies.txt ./data/policies.txt

# Ensure the FAISS index directory exists and is writable by appuser
RUN mkdir -p ./data/faiss_index \
    && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
