# ════════════════════════════════════════════════════════════════════
#  Find me in the terminal — Dockerfile
#  Multi-stage build: slim production image
# ════════════════════════════════════════════════════════════════════

# ── Stage 1: dependency builder ──────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps (needed for asyncpg C extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies into a prefix
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime image ───────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Create non-root user for security
RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid 1001 --no-create-home appuser

WORKDIR /app

# Runtime OS deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/

# Own files as non-root user
RUN chown -R appuser:appgroup /app

USER appuser

# ── Health check ─────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# ── Expose ───────────────────────────────────────────────────────────
EXPOSE 8000

# ── Run ──────────────────────────────────────────────────────────────
# uvicorn with 2 workers for a single-core container
# For production scale: use gunicorn + uvicorn workers instead
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
